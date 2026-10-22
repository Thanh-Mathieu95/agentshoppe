"""Phiếu sản phẩm: ghi trường, đọc lại, viết tin, cổng đăng tin (mục 6.1, 6.2, 9.6)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app import catalog
from app.config import ASR_CONF_THRESHOLD, pending_seconds
from app.confirm import templates as tp
from app.confirm.confusables import EMPHASIS, HIGH_RISK, emphasize_confusable
from app.confirm.engine import ConfirmationRequest, log_blocked
from app.events import res
from app.i18n.vi import cap, t
from app.models import FieldState, Image, Listing, ListingField, Risk, Seller, Source
from app.services import policy, pricing
from app.validators import numbers, sanity, sources

NUMERIC_KEYS = {"price": "price", "volume_ml": "volume", "weight_g": "weight", "stock": "stock"}


# ---------- truy vấn ----------

def fields(db: Session, listing_id: int) -> dict[str, ListingField]:
    rows = db.exec(select(ListingField).where(ListingField.listing_id == listing_id).order_by(ListingField.id)).all()
    return {f.key: f for f in rows}


def images(db: Session, listing: Listing) -> list[Image]:
    return list(db.exec(select(Image).where(Image.owner_type == "listing", Image.owner_id == listing.id)).all())


def container(listing: Listing) -> str:
    return catalog.category(listing.category)["container_word"]


def name_of(db: Session, listing: Listing) -> str:
    f = fields(db, listing.id).get("name")
    return (f.value if f and f.value else None) or listing.title or catalog.category(listing.category)["label"]


def label_of(listing: Listing, key: str) -> str:
    tpl = catalog.field_template(listing.category, key)
    return tpl["label"] if tpl else key


def active_listing(db: Session, seller_id: int) -> Listing | None:
    return db.exec(select(Listing).where(Listing.seller_id == seller_id, Listing.status.in_(["drafting", "ready"]))
                   .order_by(Listing.id.desc())).first()


def find_by_name(db: Session, seller_id: int, text: str) -> Listing | None:
    low = text.lower()
    best = None
    for lst in db.exec(select(Listing).where(Listing.seller_id == seller_id).order_by(Listing.id.desc())).all():
        n = name_of(db, lst).lower()
        if n and n in low:
            return lst
        if best is None and any(k in low for k in catalog.category(lst.category)["keywords"]):
            best = lst
    return best


def start_listing(db: Session, seller: Seller, category: str) -> Listing:
    lst = Listing(seller_id=seller.id, category=category)
    db.add(lst)
    db.commit()
    for tpl in catalog.category(category)["fields"]:
        db.add(ListingField(listing_id=lst.id, key=tpl["key"], unit=tpl.get("unit"), risk=Risk(tpl["risk"])))
    db.commit()
    return lst


# ---------- giá trị ----------

_LEAD = re.compile(r"^(dạ|vâng|ừ|à|ờ|thì|cái|của (cô|tôi|em|mình)|sản phẩm|nó|tên( nó| sản phẩm)?|là|ở|lấy ở|lấy|tại|vào|đựng|bằng|mùi|màu|khoảng|chừng|hái ở|hái vào|làm ở|tên là)\s+", re.I)
_TAIL = re.compile(r"\s+(ạ|nhé|nha|đó|đấy|thôi|cô ơi|ạ\.)$", re.I)


_NAME_LEAD = re.compile(r"^.*?\b(?:muốn |định |cần |sẽ )?(?:đăng bán|bán|đăng)(?: thêm)?\s+", re.I)
_NAME_STOP = re.compile(r"\s*[,;]|\s+(giá|mỗi|một chai|chai|hũ|gói)\b", re.I)


def name_from_utterance(text: str) -> str:
    """'Cô muốn bán mật ong rừng, giá ba trăm nghìn một chai' -> 'Mật ong rừng'."""
    t_ = _NAME_LEAD.sub("", text.strip())
    t_ = _NAME_STOP.split(t_, maxsplit=1)[0]
    toks = t_.split()
    cut = next((i for i, tok in enumerate(toks)
                if numbers.normalize_text(tok) in numbers.NUMBER_WORDS or re.match(r"^\d", tok)), len(toks))
    return cap(" ".join(toks[:cut]).strip(" ,."))


def clean_text_value(category: str, key: str, raw: str) -> str:
    if key == "name":
        return name_from_utterance(raw)
    t_ = raw.strip().strip(".,!?")
    for _ in range(4):
        t_ = _LEAD.sub("", t_).strip()
        t_ = _TAIL.sub("", t_).strip()
    tpl = catalog.field_template(category, key) or {}
    low = t_.lower()
    for choice in tpl.get("choices", []):
        last = choice.split()[-1]
        if choice in low or re.search(rf"\b{re.escape(last)}\b", low):
            return choice
    return cap(t_)


def spoken_value(listing: Listing, key: str, value: str | None) -> str:
    if value is None:
        return ""
    if key == "price":
        return tp.money_spoken(int(value))
    if key == "volume_ml":
        return tp.volume_spoken(int(value))
    if key == "weight_g":
        return tp.weight_spoken(int(value))
    if key == "stock":
        return f"{numbers.number_to_words(int(value))} {container(listing)}"
    return value


def short_value(listing: Listing, key: str, value: str | None) -> str:
    if value is None:
        return "—"
    if key == "price":
        return tp.money_digits(int(value))
    if key == "volume_ml":
        return tp.volume_short(int(value))
    if key == "weight_g":
        return f"{int(value)} g"
    if key == "stock":
        return f"{value} {container(listing)}"
    return value


# ---------- ghi trường và đọc lại ----------

def set_field(db: Session, seller: Seller, listing: Listing, key: str, raw_text: str, source: str = "voice",
              confidence: float | None = None, is_correction: bool = False) -> dict:
    fs = fields(db, listing.id)
    f = fs.get(key)
    if f is None:   # trường ngoài mẫu (ví dụ "additives" học từ câu trả lời khách)
        f = ListingField(listing_id=listing.id, key=key, risk=Risk.YELLOW)
        db.add(f)
    parsed = None
    if key in NUMERIC_KEYS:
        parsed = numbers.parse(raw_text, key)
        if not parsed:
            return res(False, say=t("NOT_A_NUMBER", seller.honorific, label=label_of(listing, key)),
                       warnings=[{"code": "NOT_A_NUMBER", "layer": 1, "params": {}}])
        value = str(parsed.int_value)
    else:
        value = clean_text_value(listing.category, key, raw_text)
        if not value:
            return res(False, say=t("field_rejected", seller.honorific, label=label_of(listing, key)))
    extra = sanity.check_contradiction(f, value, is_correction)
    f.history = [*(f.history or []), value][-10:]
    f.value = value
    f.unit = parsed.unit if parsed else f.unit
    f.state = FieldState.HEARD
    f.source = Source(source)
    f.confidence = confidence
    f.raw_utterance = raw_text
    f.confirmed_at = None
    f.updated_at = datetime.now()
    if key in ("volume_ml",) and "image_mismatch:volume_ml" in (listing.acks or []):
        listing.acks = [a for a in listing.acks if a != "image_mismatch:volume_ml"]
    if listing.status in ("drafting", "ready"):   # dữ liệu đổi -> tin phải viết và đọc lại
        listing.status = "drafting"
        listing.draft_raw = listing.description = listing.public_description = None
    db.add_all([f, listing])
    db.commit()
    if f.risk == Risk.GREEN:
        f.state = FieldState.CHECKED
        db.add(f)
        db.commit()
        return res(True, data={"key": key, "value": value, "state": f.state.value})
    req, warnings = build_confirmation(db, seller, listing, f, parsed=parsed, extra_warnings=extra, log=True)
    if not warnings:
        f.state = FieldState.CHECKED
        db.add(f)
        db.commit()
    return res(True, warnings=warnings, confirmation=req,
               data={"key": key, "value": value, "state": f.state.value, "flags": req.flags})


def _warning_text(seller: Seller, listing: Listing, w: dict) -> str:
    h = seller.honorific
    p = w["params"]
    code = w["code"]
    if code in ("PRICE_OUTLIER_LOW", "PRICE_OUTLIER_HIGH"):
        return t(code, h, min=tp.money_short(p["min"]), max=tp.money_short(p["max"]),
                 price=tp.money_spoken(p["price"]), alt=tp.money_spoken(p["alt"]))
    if code == "NEGATIVE_PAYOUT":
        return t(code, h, loss=tp.money_spoken(p["loss"]))
    if code == "STOCK_OUTLIER":
        return t(code, h, stock=numbers.number_to_words(p["stock"]), alt=numbers.number_to_words(p["alt"]))
    if code == "CONTRADICTION":
        return t(code, h, a=spoken_value(listing, p["key"], p["a"]), b=spoken_value(listing, p["key"], p["b"]))
    if code == "IMAGE_MISMATCH":
        return t(code, h, obs=f"{container(listing)} cỡ {tp.volume_spoken(int(p['obs']))}",
                 val=tp.volume_spoken(int(p["val"])))
    return t("UNIT_MISMATCH", h, label=label_of(listing, p.get("key", "")))


def build_confirmation(db: Session, seller: Seller, listing: Listing, f: ListingField, parsed=None,
                       extra_warnings=(), log: bool = False) -> tuple[ConfirmationRequest, list[dict]]:
    h = seller.honorific
    key = f.key
    if parsed is None and key in NUMERIC_KEYS and f.raw_utterance:
        parsed = numbers.parse(f.raw_utterance, key)
    if parsed and str(parsed.int_value) != f.value:
        parsed = None
    num = int(f.value) if key in NUMERIC_KEYS and f.value else None

    warnings = list(extra_warnings)
    if key == "price":
        warnings += sanity.check_price(listing.category, num)
    elif key == "stock":
        warnings += sanity.check_stock(num)
    elif key == "volume_ml" and "image_mismatch:volume_ml" not in (listing.acks or []):
        warnings += sanity.check_image(images(db, listing), key, num)

    confus = parsed.confusable_words if parsed else []
    low_conf = f.confidence is not None and f.confidence < ASR_CONF_THRESHOLD
    flags = [w["code"] for w in warnings] + [f"confusable:{w}" for w in confus]
    if parsed and parsed.assumed_unit:
        flags.append("assumed_unit")
    if low_conf:
        flags.append("low_confidence")

    if log:
        for w in warnings:
            log_blocked(db, seller.id, w["layer"], w["code"], f"listing:{listing.id}:{key}={f.value} {w['params']}")
        risky = [w for w in confus if w in HIGH_RISK]
        if risky or (low_conf and confus):
            log_blocked(db, seller.id, 1, "CONFUSABLE_NUMBER", f"{key}: '{f.raw_utterance}' ({', '.join(confus)})")
        elif low_conf:
            log_blocked(db, seller.id, 1, "LOW_CONFIDENCE", f"{key}: '{f.raw_utterance}' conf={f.confidence}")
        if parsed and parsed.assumed_unit and key == "price":
            log_blocked(db, seller.id, 1, "ASSUMED_UNIT", f"'{f.raw_utterance}' -> {f.value} VND")

    cont = container(listing)
    if warnings:
        prompt = _warning_text(seller, listing, warnings[0])
    else:
        emph_words = [w for w in confus if w in EMPHASIS][:2]
        emphasis = t("emphasis_prefix", h, words="; ".join(emphasize_confusable(w) for w in emph_words)) if emph_words else ""
        if parsed and parsed.assumed_unit and key == "price":
            emphasis += t("assumed_unit_note", h, money=tp.money_spoken(num))
        prefix = t("low_confidence_note", h) if low_conf else ""
        if key == "price":
            prompt = t("readback_price", h, name=name_of(db, listing), money=tp.money_spoken(num),
                       notes=tp.money_as_notes(num), emphasis=emphasis)
        elif key == "volume_ml":
            prompt = t("readback_volume_ml", h, container=cont, volume=tp.volume_spoken(num), emphasis=emphasis)
        elif key == "weight_g":
            prompt = t("readback_weight_g", h, container=cont, weight=tp.weight_spoken(num), emphasis=emphasis)
        elif key == "stock":
            prompt = t("readback_stock", h, stock_words=numbers.number_to_words(num), container=cont, emphasis=emphasis)
        elif key == "name":
            prompt = t("readback_name", h, value=f.value)
        else:
            prompt = t("readback_generic", h, label_cap=cap(label_of(listing, key)), value=f.value)
        prompt = prefix + prompt

    card = {"kind": "confirm", "big": short_value(listing, key, f.value), "text": cap(label_of(listing, key)),
            "risk": f.risk.value, "subject_ref": f"listing:{listing.id}:{key}"}
    if key == "price":
        card["visual"] = f"notes:{tp.notes_visual(num)}"
        card["text"] = f"Giá mỗi {cont}"
    elif key == "volume_ml":
        card["visual"] = f"volume:{num}"
    elif key == "stock":
        card["visual"] = f"count:{num}"
    if warnings:
        w = warnings[0]
        card["warning"] = {"PRICE_OUTLIER_LOW": "Giá thấp bất thường", "PRICE_OUTLIER_HIGH": "Giá cao bất thường",
                           "NEGATIVE_PAYOUT": "Bán giá này bị lỗ", "IMAGE_MISMATCH": "Ảnh khác lời nói",
                           "STOCK_OUTLIER": "Số lượng lạ", "CONTRADICTION": "Hai lần nói khác nhau"}.get(w["code"], "Cần kiểm tra")
        alt = w["params"].get("alt") or (w["params"].get("obs") if w["code"] == "IMAGE_MISMATCH" else None)
        if alt:
            card["alt"] = {"big": short_value(listing, key, str(int(alt))), "value": str(int(alt))}
    if flags:
        card["flags"] = flags

    req = ConfirmationRequest(
        seller_id=seller.id, subject_ref=f"listing:{listing.id}:{key}", kind="field", risk=f.risk,
        prompt_text=prompt, value_display={"key": key, "number": num, "value": f.value, "unit": f.unit},
        flags=flags, card=card, payload={"warnings": [w["code"] for w in warnings]},
    )
    return req, warnings


def confirm_field(db: Session, listing: Listing, key: str, req: ConfirmationRequest) -> ListingField:
    """Chỉ ConfirmationEngine gọi (qua effects.apply)."""
    f = fields(db, listing.id)[key]
    f.state = FieldState.CONFIRMED
    f.confirmed_at = datetime.now()
    if key == "stock":
        listing.stock = int(f.value)
    if "IMAGE_MISMATCH" in req.flags:
        listing.acks = [*(listing.acks or []), f"image_mismatch:{key}"]
    db.add_all([f, listing])
    db.commit()
    return f


def unconfirmed(db: Session, listing: Listing) -> list[ListingField]:
    return [f for f in fields(db, listing.id).values()
            if f.risk != Risk.GREEN and f.state in (FieldState.HEARD, FieldState.CHECKED)]


def next_missing(db: Session, listing: Listing) -> dict | None:
    fs = fields(db, listing.id)
    for tpl in catalog.category(listing.category)["fields"]:
        f = fs.get(tpl["key"])
        if f and f.state == FieldState.EMPTY and "skipped" not in (f.history or []):
            return tpl
    return None


def skip_field(db: Session, listing: Listing, key: str) -> bool:
    f = fields(db, listing.id).get(key)
    if not f or f.risk != Risk.GREEN:
        return False
    f.history = [*(f.history or []), "skipped"]
    db.add(f)
    db.commit()
    return True


def has_accepted_photo(db: Session, listing: Listing) -> bool:
    return any(i.accepted for i in images(db, listing))


# ---------- giá, quy định ----------

def price_report(db: Session, seller: Seller, listing: Listing) -> dict:
    fs = fields(db, listing.id)
    price = int(fs["price"].value)
    pc = pricing.price_check(listing.category, price)
    say = t("price_report", seller.honorific, min=tp.money_short(pc["min"]), max=tp.money_short(pc["max"]),
            container=container(listing), fee=tp.money_short(pc["fee"]), packaging=tp.money_short(pc["packaging"]),
            payout=tp.money_spoken(pc["payout"]))
    pol = policy.check(listing.category)
    if pol["rules"]:
        say += " " + t("policy_note", seller.honorific, say=pol["rules"][0]["say"])
    listing.price_checked = True
    db.add(listing)
    db.commit()
    return res(True, say=say, data=pc)


# ---------- viết tin ----------

def draft_text_rules(db: Session, listing: Listing) -> tuple[str, str]:
    fs = {k: f for k, f in fields(db, listing.id).items() if f.state == FieldState.CONFIRMED or f.state == FieldState.CHECKED}
    v = {k: f.value for k, f in fs.items() if f.value}
    cont = container(listing)
    sent = []
    name = v.get("name", catalog.category(listing.category)["label"])
    if "origin" in v:
        sent.append(f"{name} {'lấy' if listing.category == 'honey' else 'làm'} ở {v['origin']} [name][origin].")
    else:
        sent.append(f"{name} [name].")
    if "volume_ml" in v:
        holder = v.get("container", cont)
        sent.append(f"Mỗi {holder.lower()} {tp.volume_short(int(v['volume_ml']))} [volume_ml]" + ("[container]." if "container" in v else "."))
    if "weight_g" in v:
        sent.append(f"Mỗi {cont} nặng {v['weight_g']} gam [weight_g].")
    for key in ("harvest_time", "processing", "material", "size", "color", "scent", "burn_hours", "expiry", "maker"):
        if key in v:
            sent.append(f"{cap(label_of(listing, key))}: {v[key]} [{key}].")
    if "storage" in v:
        sent.append(f"Bảo quản: {v['storage']} [storage].")
    extra = policy.check(listing.category)["auto_append"]
    if extra:
        sent.append(f"{extra} [policy]")
    title_bits = [name]
    if "origin" in v:
        place = v["origin"].split(",")[-1].strip()
        if place.lower() not in name.lower():
            title_bits.append(place)
    if "volume_ml" in v:
        title_bits.append(f"{v['volume_ml']}ml")
    if "weight_g" in v:
        title_bits.append(f"{v['weight_g']}g")
    return " ".join(title_bits), " ".join(sent)


def save_draft(db: Session, seller: Seller, listing: Listing, title: str, tagged: str) -> dict:
    fs = fields(db, listing.id)
    def deferred_green(code, detail):   # trường XANH được xác nhận ở bản tóm tắt cuối, không phải lỗi
        f = fs.get(detail.split(":")[0]) if code == "SOURCE_NOT_CONFIRMED" else None
        return f is not None and f.risk == Risk.GREEN and f.state == FieldState.CHECKED

    errors = [e for e in sources.check(tagged, fs) if not deferred_green(*e)]
    for code, detail in errors:
        log_blocked(db, seller.id, 3, code, detail)
    clean_tagged, public = sources.clean(tagged, fs)
    for claim in sources.BANNED_CLAIMS:
        if claim in title.lower() and not sources.seller_said(fs, claim):
            title = re.sub(re.escape(claim), "", title, flags=re.I).strip()
            log_blocked(db, seller.id, 3, "BANNED_CLAIM", f"title: {claim}")
    listing.title = re.sub(r"\s{2,}", " ", title)
    listing.draft_raw = tagged
    listing.description = clean_tagged
    listing.public_description = public
    db.add(listing)
    db.commit()
    return res(True, data={"title": listing.title, "description": public, "removed": [e[1] for e in errors]},
               warnings=[{"code": c, "layer": 3, "params": {"detail": d}} for c, d in errors])


# ---------- cổng đăng tin ----------

def can_publish(db: Session, seller: Seller, listing: Listing, log: bool = True) -> list[tuple[str, str | None]]:
    errors: list[tuple[str, str | None]] = []
    fs = fields(db, listing.id)
    for f in fs.values():
        if f.risk in (Risk.RED, Risk.YELLOW) and f.state != FieldState.CONFIRMED:
            errors.append(("NOT_CONFIRMED", f.key))
    errors += sanity.check_listing(listing.category, fs)
    vol = fs.get("volume_ml")
    if vol and vol.value and "image_mismatch:volume_ml" not in (listing.acks or []):
        for w in sanity.check_image(images(db, listing), "volume_ml", int(vol.value)):
            errors.append(("IMAGE_MISMATCH", "volume_ml"))
    if not listing.description:
        errors.append(("NO_DESCRIPTION", None))
    else:
        errors += [(c, d) for c, d in sources.check(listing.description, fs)]
    if not has_accepted_photo(db, listing):
        errors.append(("NO_ACCEPTED_PHOTO", None))
    if log:
        for code, detail in errors:
            layer = 3 if code in ("IMAGE_MISMATCH", "UNSOURCED_SENTENCE", "SOURCE_NOT_CONFIRMED", "BANNED_CLAIM") else 5
            log_blocked(db, seller.id, layer, code, f"publish listing:{listing.id} {detail or ''}")
    return errors


def gate_reason(seller: Seller, listing: Listing, errors: list) -> str:
    code, detail = errors[0]
    h = seller.honorific
    if code == "NOT_CONFIRMED":
        return t("gate_NOT_CONFIRMED", h, label=label_of(listing, detail))
    if code == "NO_ACCEPTED_PHOTO":
        return t("gate_NO_ACCEPTED_PHOTO", h)
    if code in ("UNSOURCED_SENTENCE", "SOURCE_NOT_CONFIRMED", "BANNED_CLAIM", "NO_DESCRIPTION"):
        return t("gate_SOURCE", h)
    return t("gate_SANITY", h)


def request_publish(db: Session, seller: Seller, listing: Listing) -> dict:
    errors = can_publish(db, seller, listing)
    if errors:
        return res(False, say=t("gate_blocked", seller.honorific, reason=gate_reason(seller, listing, errors)),
                   warnings=[{"code": c, "layer": 5, "params": {"detail": d}} for c, d in errors])
    listing.status = "ready"
    db.add(listing)
    db.commit()
    fs = fields(db, listing.id)
    v = {k: f.value for k, f in fs.items() if f.value}
    extras = []
    if "volume_ml" in v:
        extras.append(f"Mỗi {container(listing)} {tp.volume_spoken(int(v['volume_ml']))}")
    if "weight_g" in v:
        extras.append(f"Mỗi {container(listing)} {tp.weight_spoken(int(v['weight_g']))}")
    if "origin" in v:
        extras.append(f"lấy ở {v['origin']}")
    prompt = t("publish_summary", seller.honorific, name=v["name"], money=tp.money_spoken(int(v["price"])),
               extras=", ".join(extras) or "", stock_words=numbers.number_to_words(int(v["stock"])),
               container=container(listing)).replace(" . ", " ").replace("..", ".")
    rows = [{"label": cap(label_of(listing, k)), "value": short_value(listing, k, f.value), "key": k}
            for k, f in fs.items() if f.value and "skipped" != f.value]
    req = ConfirmationRequest(
        seller_id=seller.id, subject_ref=f"listing:{listing.id}:publish", kind="action", risk=Risk.RED,
        prompt_text=prompt, two_step=True, action_phrase="đăng đi",
        value_display={"summary": rows}, flags=[],
        card={"kind": "summary", "title": listing.title, "rows": rows, "big": tp.money_digits(int(v["price"])),
              "text": "Đăng tin này?", "risk": "red", "two_step": True, "image_ids": listing.image_ids},
    )
    return res(True, confirmation=req, data={"summary": rows})


def publish(db: Session, listing: Listing) -> Listing:
    for f in fields(db, listing.id).values():
        if f.risk == Risk.GREEN and f.value and f.state != FieldState.CONFIRMED:
            f.state = FieldState.CONFIRMED
            f.confirmed_at = datetime.now()
            db.add(f)
    db.commit()
    if listing.draft_raw:   # câu về trường XANH giờ mới có nguồn đã xác nhận
        fs = fields(db, listing.id)
        listing.description, listing.public_description = sources.clean(listing.draft_raw, fs)
    listing.status = "pending_publish"
    listing.pending_until = datetime.now() + timedelta(seconds=pending_seconds())
    db.add(listing)
    db.commit()
    return listing


def finalize_due(db: Session, force: bool = False) -> list[Listing]:
    q = select(Listing).where(Listing.status == "pending_publish")
    out = []
    for lst in db.exec(q).all():
        if force or (lst.pending_until and lst.pending_until <= datetime.now()):
            lst.status = "published"
            lst.pending_until = None
            db.add(lst)
            out.append(lst)
    db.commit()
    return out


def undo(db: Session, seller: Seller) -> dict:
    lst = db.exec(select(Listing).where(Listing.seller_id == seller.id, Listing.status == "pending_publish")
                  .order_by(Listing.id.desc())).first()
    if not lst:
        return res(False, say=t("undo_nothing", seller.honorific))
    lst.status = "drafting"
    lst.pending_until = None
    db.add(lst)
    db.commit()
    return res(True, say=t("undo_done", seller.honorific), data={"listing_id": lst.id})


# ---------- sửa tin đang bán ----------

def request_price_change(db: Session, seller: Seller, listing: Listing, raw_text: str) -> dict:
    p = numbers.parse(raw_text, "price")
    if not p:
        return res(False, say=t("NOT_A_NUMBER", seller.honorific, label="giá"))
    fs = fields(db, listing.id)
    old = int(fs["price"].value)
    new = p.int_value
    pay = pricing.payout(listing.category, new)["payout"]
    warnings = sanity.check_price(listing.category, new)
    for w in warnings:
        log_blocked(db, seller.id, w["layer"], w["code"], f"price_change listing:{listing.id} -> {new}")
    prompt = (_warning_text(seller, listing, warnings[0]) + " ") if warnings else ""
    prompt += t("price_change_prompt", seller.honorific, name=name_of(db, listing), old=tp.money_short(old),
                new=tp.money_spoken(new), container=container(listing), payout=tp.money_short(pay))
    req = ConfirmationRequest(
        seller_id=seller.id, subject_ref=f"listing:{listing.id}:price_change", kind="action", risk=Risk.RED,
        prompt_text=prompt, two_step=True, action_phrase="đổi giá",
        value_display={"key": "price", "number": new}, flags=[w["code"] for w in warnings],
        card={"kind": "confirm", "big": tp.money_digits(new), "visual": f"notes:{tp.notes_visual(new)}",
              "text": f"Giá mới, cũ {tp.money_digits(old)}", "risk": "red", "two_step": True},
        payload={"new_price": new},
    )
    return res(True, confirmation=req)


def request_stock_update(db: Session, seller: Seller, listing: Listing, raw_text: str) -> dict:
    p = numbers.parse(raw_text, "stock")
    if not p:
        return res(False, say=t("NOT_A_NUMBER", seller.honorific, label="số lượng"))
    n = p.int_value
    warnings = sanity.check_stock(n)
    emph = [w for w in p.confusable_words if w in EMPHASIS][:1]
    prompt = (_warning_text(seller, listing, warnings[0]) + " ") if warnings else ""
    if emph:
        prompt += t("emphasis_prefix", seller.honorific, words=emphasize_confusable(emph[0]))
    prompt += t("stock_prompt", seller.honorific, name=name_of(db, listing), stock_words=numbers.number_to_words(n),
                container=container(listing))
    req = ConfirmationRequest(
        seller_id=seller.id, subject_ref=f"listing:{listing.id}:stock_update", kind="action", risk=Risk.RED,
        prompt_text=prompt, value_display={"key": "stock", "number": n},
        flags=[f"confusable:{w}" for w in p.confusable_words],
        card={"kind": "confirm", "big": f"{n} {container(listing)}", "visual": f"count:{n}", "text": name_of(db, listing), "risk": "red"},
        payload={"stock": n},
    )
    return res(True, confirmation=req)


def apply_stock(db: Session, listing: Listing, n: int) -> None:
    f = fields(db, listing.id)["stock"]
    f.value = str(n)
    f.state = FieldState.CONFIRMED
    f.confirmed_at = datetime.now()
    f.history = [*(f.history or []), str(n)][-10:]
    listing.stock = n
    if n > 0 and listing.status == "hidden":
        listing.status = "published"
    db.add_all([f, listing])
    db.commit()


def apply_price(db: Session, listing: Listing, price: int) -> None:
    f = fields(db, listing.id)["price"]
    f.value = str(price)
    f.state = FieldState.CONFIRMED
    f.confirmed_at = datetime.now()
    f.history = [*(f.history or []), str(price)][-10:]
    db.add(f)
    db.commit()
