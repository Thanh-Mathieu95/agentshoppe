"""Luồng hội thoại: xử lý xác nhận, hiệu lực sau xác nhận, đi tiếp phiếu, ảnh, và bộ định tuyến luật."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, select

from app import catalog
from app.agent import llm
from app.agent.session import Session as ConvSession
from app.config import MAX_PHOTO_ATTEMPTS
from app.confirm import engine
from app.confirm import templates as tp
from app.confirm.engine import ConfirmationRequest, log_blocked, log_confirmation
from app.events import card, open_camera, speak
from app.i18n.vi import CANCEL_REASONS, MODE_LABEL, cap, t
from app.models import (BuyerMessage, FieldState, GrowthSuggestion, GuardianApproval, Image, Listing, Mode, Order,
                        Risk, Seller)
from app.services import growth, orders as osv, shopmaker, support, vision
from app.services import listings as ls
from app.validators import numbers, sanity

log = logging.getLogger(__name__)


@dataclass
class Ctx:
    db: Session
    seller: Seller
    s: ConvSession
    text: str = ""
    button: str | None = None
    confidence: float | None = None
    latency_ms: int | None = None

    @property
    def h(self) -> str:
        return self.seller.honorific

    def say(self, key: str, priority: str = "normal", **kw) -> dict:
        return speak(t(key, self.h, **kw), priority)


def norm(text: str) -> str:
    return numbers.normalize_text(text)


def has(text: str, *phrases: str) -> bool:
    return any(p in text for p in phrases)


# =====================================================================
# Xác nhận
# =====================================================================

def ask_confirmation(ctx: Ctx, req: ConfirmationRequest) -> list[dict]:
    req.asked_at = datetime.now()
    ctx.s.pending = req
    ctx.s.awaiting = None
    c = {**req.card, "subject_ref": req.subject_ref, "two_step": req.two_step, "risk": req.risk.value,
         "action_phrase": req.action_phrase, "confirm_id": req.id}
    c.setdefault("kind", "confirm")
    return [speak(req.prompt_text, "confirm" if req.risk == Risk.RED else "normal"), card(**c)]


def _reask(ctx: Ctx, req: ConfirmationRequest, prefix: str = "") -> list[dict]:
    req.asked_at = datetime.now()
    text = (prefix + " " + req.prompt_text).strip()
    return [speak(text, "confirm"), card(**{**req.card, "subject_ref": req.subject_ref, "two_step": req.two_step,
                                           "risk": req.risk.value, "action_phrase": req.action_phrase, "confirm_id": req.id})]


def _open_question_for(ctx: Ctx, req: ConfirmationRequest) -> str:
    key = req.value_display.get("key")
    lid = int(req.subject_ref.split(":")[1])
    lst = ctx.db.get(Listing, lid)
    tpl = catalog.field_template(lst.category, key) if lst else None
    q = tpl["ask"].format(h=ctx.h, H=cap(ctx.h)) if tpl else "con số đó là bao nhiêu?"
    return q[0].lower() + q[1:]


async def handle_pending(ctx: Ctx) -> list[dict]:
    db, s, req = ctx.db, ctx.s, ctx.s.pending
    now = datetime.now()
    if ctx.button == "timeout":
        req.timeouts += 1
        if req.timeouts == 1:
            return _reask(ctx, req, t("confirm_timeout_reask", ctx.h, prompt="").strip())
        log_confirmation(db, req, "timeout", None, None)
        s.pending = None
        return [ctx.say("confirm_timeout_final")]

    r = engine.resolve(req, ctx.text, ctx.button)
    ms = ctx.latency_ms if ctx.latency_ms is not None else int((now - req.asked_at).total_seconds() * 1000)
    response = ctx.text or ctx.button

    if r.kind == "control":
        if r.control == "repeat":
            return _reask(ctx, req)
        if r.control == "slower":
            ctx.seller.tts_speed = round(max(0.6, ctx.seller.tts_speed - 0.1), 2)
            db.add(ctx.seller)
            db.commit()
            return _reask(ctx, req, t("slower_ok", ctx.h))
        log_confirmation(db, req, "unclear", response, ms)
        s.pending = None
        return [ctx.say("stopped")]

    if r.kind == "clarify":
        req.attempts += 1
        log_confirmation(db, req, "unclear", response, ms)
        req.asked_at = now
        if r.reason == "explicit_yes":
            log_blocked(db, ctx.seller.id, 4, "EXPLICIT_YES_REQUIRED", f"{req.subject_ref}: '{response}'")
            text = t("clarify_explicit_yes", ctx.h)
        elif r.reason == "say_action_phrase":
            text = t("clarify_action_phrase", ctx.h, phrase=req.action_phrase)
        elif r.reason == "open_question":
            text = t("rubber_stamp_question", ctx.h, question=req.open_question)
        else:
            text = t("clarify_unclear", ctx.h)
        return [speak(text, "confirm"), card(**{**req.card, "subject_ref": req.subject_ref, "two_step": req.two_step,
                                                "risk": req.risk.value, "action_phrase": req.action_phrase})]

    if r.kind == "rejected":
        log_confirmation(db, req, "rejected", response, ms)
        s.pending = None
        return on_rejected(ctx, req)

    if r.kind == "corrected":
        log_confirmation(db, req, "corrected", response, ms)
        s.pending = None
        pre = []
        if req.open_question:
            log_blocked(db, ctx.seller.id, 4, "RUBBER_STAMP",
                        f"{req.subject_ref}: đã xác nhận {req.number}, hỏi lại nói {r.new_value.int_value}")
            lid, key = int(req.subject_ref.split(":")[1]), req.value_display["key"]
            lst = db.get(Listing, lid)
            pre = [ctx.say("rubber_stamp_mismatch", old=ls.spoken_value(lst, key, str(req.number)),
                           new=ls.spoken_value(lst, key, str(r.new_value.int_value)))]
        return pre + await on_corrected(ctx, req)

    # confirmed
    if req.open_question:
        log_confirmation(db, req, "confirmed", response, ms)
        s.pending = None
        return [ctx.say("rubber_stamp_ok")] + await apply_confirmed(ctx, req)
    if engine.needs_open_question(db, req):
        log_confirmation(db, req, "rubber_stamp_check", response, ms)
        req.open_question = _open_question_for(ctx, req)
        req.attempts = 0
        req.asked_at = now
        req.flags = [*req.flags, "rubber_stamp_check"]
        return [speak(t("rubber_stamp_question", ctx.h, question=req.open_question), "confirm"),
                card(kind="ask_number", text=cap(req.open_question), key=req.value_display.get("key"))]
    log_confirmation(db, req, "confirmed", response, ms)
    s.pending = None
    return await apply_confirmed(ctx, req)


def on_rejected(ctx: Ctx, req: ConfirmationRequest) -> list[dict]:
    typ, oid, what = req.subject_ref.split(":")[:3]
    oid = int(oid)
    if typ == "listing" and req.kind == "field":
        lst = ctx.db.get(Listing, oid)
        ctx.s.awaiting = ("field", oid, what)
        return [ctx.say("field_rejected", label=ls.label_of(lst, what)), card(kind="ask", text=f"Nói lại {ls.label_of(lst, what)}")]
    if typ == "image":
        img = ctx.db.get(Image, oid)
        ctx.s.awaiting = ("photo", "listing", img.owner_id)
        return [speak(f"Vậy {ctx.h} chụp lại giúp tôi nhé."), open_camera("listing", "Đặt sản phẩm giữa khung, chỗ sáng", img.owner_id)]
    if typ == "listing" and what == "publish":
        lst = ctx.db.get(Listing, oid)
        lst.status = "drafting"
        ctx.db.add(lst)
        ctx.db.commit()
        ctx.s.awaiting = ("wrong_which", oid)
        opts = ["tên", "giá", "số lượng"]
        return [ctx.say("summary_rejected", options=", ".join(opts[:-1]) + " hay " + opts[-1]),
                card(kind="choices", text="Sai chỗ nào?", options=opts)]
    if typ == "message":
        ctx.s.awaiting = ("seller_reply", oid)
        return [speak(f"Vậy {ctx.h} nói lại câu trả lời giúp tôi.")]
    return [ctx.say("action_cancelled")]


async def on_corrected(ctx: Ctx, req: ConfirmationRequest) -> list[dict]:
    typ, oid, what = req.subject_ref.split(":")[:3]
    lst = ctx.db.get(Listing, int(oid)) if typ == "listing" else None
    if typ == "listing" and req.kind == "field":
        r = ls.set_field(ctx.db, ctx.seller, lst, what, ctx.text, confidence=ctx.confidence, is_correction=True)
        return ask_confirmation(ctx, r["confirmation"]) if r["confirmation"] else [speak(r["say"])]
    if what == "stock_update":
        r = ls.request_stock_update(ctx.db, ctx.seller, lst, ctx.text)
    elif what == "price_change":
        r = ls.request_price_change(ctx.db, ctx.seller, lst, ctx.text)
    else:
        return [ctx.say("action_cancelled")]
    return ask_confirmation(ctx, r["confirmation"]) if r["confirmation"] else [speak(r["say"])]


# =====================================================================
# Hiệu lực sau khi người bán đã xác nhận (chỉ được gọi từ handle_pending / guardian)
# =====================================================================

async def apply_confirmed(ctx: Ctx, req: ConfirmationRequest) -> list[dict]:
    if (ctx.seller.guardian_required and req.risk == Risk.RED and req.kind == "action"
            and not req.payload.get("guardian_ok")):
        ga = GuardianApproval(seller_id=ctx.seller.id, subject_ref=req.subject_ref, summary=req.prompt_text, payload=req.to_dict())
        ctx.db.add(ga)
        ctx.db.commit()
        log_blocked(ctx.db, ctx.seller.id, 5, "WAITING_GUARDIAN", req.subject_ref)
        return [ctx.say("guardian_sent", guardian=ctx.seller.guardian_name or "người bảo trợ")]
    return await execute(ctx, req)


async def execute(ctx: Ctx, req: ConfirmationRequest) -> list[dict]:
    db, s = ctx.db, ctx.s
    typ, oid, what = req.subject_ref.split(":")[:3]
    oid = int(oid)

    if typ == "listing":
        lst = db.get(Listing, oid)
        if req.kind == "field":
            ls.confirm_field(db, lst, what, req)
            return await continue_listing(ctx, lst)
        if what == "publish":
            ls.publish(db, lst)
            return [listing_event(db, lst), ctx.say("publish_pending", wait=wait_words(lst)),
                    card(kind="published", big="✓", text="Tin đang chờ lên sàn", listing_id=lst.id, undo=True)]
        if what == "price_change":
            ls.apply_price(db, lst, req.payload["new_price"])
            return [ctx.say("price_change_done", new=tp.money_spoken(req.payload["new_price"]))]
        if what == "stock_update":
            ls.apply_stock(db, lst, req.payload["stock"])
            return [ctx.say("stock_done", stock_words=numbers.number_to_words(req.payload["stock"]), container=ls.container(lst))]
        if what == "title":
            lst.title = req.payload["title"]
            db.add(lst)
            db.commit()
            return [ctx.say("title_done")]
        if what == "republish":
            lst.status = "published"
            db.add(lst)
            db.commit()
            return [ctx.say("republished", name=ls.name_of(db, lst))]

    if typ == "image":
        img = db.get(Image, oid)
        lst = db.get(Listing, img.owner_id)
        img.accepted = True
        lst.image_ids = [*(lst.image_ids or []), img.id]
        db.add_all([img, lst])
        db.commit()
        s.photo_attempts = 0
        s.best_photo_id = None
        vol = ls.fields(db, lst.id).get("volume_ml")
        if vol and vol.value and vol.state == FieldState.CONFIRMED:
            w = sanity.check_image([img], "volume_ml", int(vol.value))
            if w:
                vol.state = FieldState.HEARD
                db.add(vol)
                db.commit()
                req2, _ = ls.build_confirmation(db, ctx.seller, lst, vol, extra_warnings=[], log=True)
                return ask_confirmation(ctx, req2)
        return [ctx.say("photo_ok")] + await continue_listing(ctx, lst)

    if typ == "order":
        order = db.get(Order, oid)
        say = osv.apply_action(db, ctx.seller, order, what, req.payload)
        s.active_order_id = order.id
        ev = [speak(say), card(**osv.order_card(db, order))]
        if what == "mark_packed" or what == "packing_override":
            s.awaiting = ("photo", "receipt", order.id)
        if what in ("mark_shipped", "cancel"):   # xong một đơn -> dẫn sang việc kế tiếp
            nxt = await next_task(ctx)
            if nxt and nxt[0].get("type") == "speak" and "không còn việc gì gấp" not in nxt[0]["text"]:
                nxt[0]["text"] = "Việc tiếp theo: " + nxt[0]["text"]
            return ev + nxt
        return ev

    if typ == "message":
        msg = db.get(BuyerMessage, oid)
        s.active_message_id = None
        return [speak(support.apply_reply(db, ctx.seller, msg, req.payload["answer"], req.payload.get("raw", "")))]

    if typ == "seller" and what == "profile":
        ctx.seller.onboarded = True
        ctx.seller.uses_assistant = True
        db.add(ctx.seller)
        db.commit()
        from app.agent.rt_tools import profile_event
        return [profile_event(ctx.seller), speak(f"Dạ, hồ sơ cửa hàng {ctx.seller.shop_name} đã lưu xong.")]

    if typ == "seller" and what == "mode":
        ctx.seller.mode = Mode(req.payload["mode"])
        db.add(ctx.seller)
        db.commit()
        return [ctx.say(f"mode_changed_{req.payload['mode']}"), {"type": "mode", "mode": req.payload["mode"]}]
    return []


def wait_words(lst: Listing) -> str:
    """'mười phút' / 'mười giây' (chế độ demo)."""
    sec = max(1, round((lst.pending_until - datetime.now()).total_seconds())) if lst.pending_until else 0
    if sec < 60:
        return f"{numbers.number_to_words(sec)} giây"
    return f"{numbers.number_to_words(max(1, round(sec / 60)))} phút"


async def guardian_decide(db: Session, seller: Seller, s: ConvSession, ga: GuardianApproval, approve: bool) -> list[dict]:
    ga.status = "approved" if approve else "rejected"
    db.add(ga)
    db.commit()
    ctx = Ctx(db=db, seller=seller, s=s)
    who = seller.guardian_name or "người bảo trợ"
    if not approve:
        return [ctx.say("guardian_rejected", guardian=who, summary=ga.summary[:80])]
    req = ConfirmationRequest.from_dict(ga.payload)
    req.payload["guardian_ok"] = True
    ev = await execute(ctx, req)
    if ev and ev[0].get("type") == "speak":
        ev[0]["text"] = t("guardian_approved", seller.honorific, guardian=who) + ev[0]["text"]
    return ev


# =====================================================================
# Phiếu sản phẩm: đi tiếp từng bước, mỗi lượt một câu hỏi
# =====================================================================

def listing_event(db: Session, lst: Listing) -> dict:
    """Thẻ tin đăng trên điện thoại: hiện ngay từng thông tin và ảnh."""
    fs = ls.fields(db, lst.id)
    return {"type": "listing_live", "listing_id": lst.id, "title": ls.name_of(db, lst), "status": lst.status,
            "fields": [{"key": k, "label": ls.label_of(lst, k), "value": ls.short_value(lst, k, f.value) if f.value else None,
                        "state": f.state.value, "required": f.risk != Risk.GREEN} for k, f in fs.items()],
            "images": [f"/api/images/{i}/file" for i in (lst.image_ids or [])]}


async def continue_listing(ctx: Ctx, lst: Listing) -> list[dict]:
    db, s = ctx.db, ctx.s
    s.active_listing_id = lst.id
    if lst.status not in ("drafting", "ready"):
        return []
    live = [listing_event(db, lst)]
    pend = ls.unconfirmed(db, lst)
    if pend:
        req, _ = ls.build_confirmation(db, ctx.seller, lst, pend[0])
        return live + ask_confirmation(ctx, req)
    fs = ls.fields(db, lst.id)
    if fs["name"].state == FieldState.CONFIRMED and not ls.has_accepted_photo(db, lst):
        s.awaiting = ("photo", "listing", lst.id)
        return live + [ctx.say("ask_photo"), open_camera("listing", "Đặt sản phẩm giữa khung, chỗ sáng", lst.id)]
    tpl = ls.next_missing(db, lst)
    if tpl:
        s.awaiting = ("field", lst.id, tpl["key"])
        q = tpl["ask"].format(h=ctx.h, H=cap(ctx.h))
        if tpl["key"] == "price":   # chưa nói giá: kể giá trên sàn để người bán dễ quyết
            m = catalog.market(lst.category)
            q = (f"Trên sàn, hàng giống thế này đang bán khoảng {tp.money_short(m['min'])} đến {tp.money_short(m['max'])}, "
                 f"{m['unit_note']}. ") + q
        if tpl.get("choices"):
            c = card(kind="choices", text=q, options=tpl["choices"])
        elif tpl["key"] in ls.NUMERIC_KEYS:
            c = card(kind="ask_number", text=q, key=tpl["key"], unit=tpl.get("unit"))
        else:
            c = card(kind="ask", text=q, key=tpl["key"], skippable=tpl["risk"] == "green")
        return live + [speak(q), c]
    pre = live
    media = await shopmaker.finish_media(db, ctx.seller, lst)
    if media:
        from app.agent.rt_tools import address_words
        me = address_words(ctx.seller)[1]
        pre = [listing_event(db, lst), speak(f"{cap(me)} đã làm thêm ảnh quảng cáo: {', '.join(media)}. "
                                             "Hàng trong ảnh là ảnh thật của mình, chỉ thay nền.")]
    if not lst.price_checked:
        pre.append(speak(ls.price_report(db, ctx.seller, lst)["say"]))
    if not lst.draft_raw:
        title, tagged = await draft_listing(ctx, lst)
        if ls.save_draft(db, ctx.seller, lst, title, tagged)["warnings"]:
            # bản AI viết có câu không có nguồn -> dùng bản ghép từ thông tin đã xác nhận, không để người bán kẹt
            ls.save_draft(db, ctx.seller, lst, *ls.draft_text_rules(db, lst))
    r = ls.request_publish(db, ctx.seller, lst)
    if not r["ok"]:
        return pre + [speak(r["say"])]
    return pre + ask_confirmation(ctx, r["confirmation"])


DRAFT_SYSTEM = """Bạn viết tin đăng Shopee ngắn gọn, mộc mạc, đúng sự thật bằng tiếng Việt.
CHỈ dùng thông tin trong JSON. Mỗi câu trong mô tả PHẢI kết thúc bằng thẻ [key] của trường đã dùng (ví dụ [origin]).
Không viết: nguyên chất, 100%, tốt nhất, số 1, chữa bệnh, cam kết, thần dược.
Trả về JSON: {"title": "dưới 60 ký tự", "description_tagged": "3-5 câu"}"""


async def draft_listing(ctx: Ctx, lst: Listing) -> tuple[str, str]:
    rule_title, rule_desc = ls.draft_text_rules(ctx.db, lst)
    if not llm.enabled():
        return rule_title, rule_desc
    facts = {k: f.value for k, f in ls.fields(ctx.db, lst.id).items() if f.value and f.state in (FieldState.CONFIRMED, FieldState.CHECKED)}
    try:
        out = llm._json_from(await llm.complete_text(DRAFT_SYSTEM, json.dumps({"category": lst.category, "fields": facts}, ensure_ascii=False)))
        title, desc = out.get("title"), out.get("description_tagged")
        if title and desc:
            extra = catalog.policies().get(lst.category, {}).get("auto_append")
            return title, desc.rstrip() + (f"\n{extra} [policy]" if extra else "")
    except Exception as e:
        log.warning("draft via llm failed: %s", e)
    return rule_title, rule_desc


# =====================================================================
# Ảnh
# =====================================================================

async def on_image(ctx: Ctx, image_id: int, purpose: str) -> list[dict]:
    db, s = ctx.db, ctx.s
    img = db.get(Image, image_id)
    if not img:
        return [speak("Tôi chưa nhận được ảnh. Chụp lại giúp tôi nhé.")]
    if purpose == "listing" and s.quick_since:
        return await quick_from_photo(ctx, img)
    if purpose == "listing":
        lst = db.get(Listing, s.active_listing_id) if s.active_listing_id else ls.active_listing(db, ctx.seller.id)
        if not lst:
            return [ctx.say("ask_category")]
        img.owner_type, img.owner_id = "listing", lst.id
        a = await vision.assess(img, "listing")
        img.quality = a["quality"]
        img.observations = {**(img.observations or {}), **a["observations"]}
        img.description = a["description"]
        db.add(img)
        db.commit()
        s.photo_attempts += 1
        if a["issue"]:
            best = db.get(Image, s.best_photo_id) if s.best_photo_id else None
            score = img.quality.get("bright", 0) * img.quality.get("sharp", 0)
            if not best or score > best.quality.get("bright", 0) * best.quality.get("sharp", 0):
                s.best_photo_id = img.id
            if s.photo_attempts >= MAX_PHOTO_ATTEMPTS:
                best = db.get(Image, s.best_photo_id)
                pre = [ctx.say("photo_give_up", guardian=ctx.seller.guardian_name or "người nhà")]
                return pre + _describe_photo(ctx, best)
            s.awaiting = ("photo", "listing", lst.id)
            return [ctx.say(f"photo_guide_{a['issue']}"), open_camera("listing", _guide_short(a["issue"]), lst.id)]
        return _describe_photo(ctx, img)

    order = _order_for_photo(ctx)
    if not order:
        return [ctx.say("order_not_found")]
    s.active_order_id = order.id
    if purpose == "packing_check":
        img.owner_type, img.owner_id = "order_packing", order.id
        a = await vision.assess(img, "packing_check")
        img.quality = a["quality"]
        db.add(img)
        db.commit()
        r = osv.packing_result(db, ctx.seller, order, img, a)
        ev = [speak(r["say"], "normal" if r["ok"] else "confirm"), card(**osv.order_card(db, order))]
        if not r["ok"]:
            ev.append(open_camera("packing_check", "Bày đủ hàng của đơn lên bàn", order.id))
        return ev
    # receipt
    img.owner_type, img.owner_id = "receipt", order.id
    a = await vision.assess(img, "receipt")
    img.observations = {**(img.observations or {}), **a["observations"]}
    db.add(img)
    db.commit()
    if a["issue"]:
        return [ctx.say(f"photo_guide_{a['issue']}"), open_camera("receipt", _guide_short(a["issue"]), order.id)]
    code = a["observations"].get("tracking_code")
    if not code:
        s.awaiting = ("tracking", order.id)
        return [ctx.say("receipt_unsure"), card(kind="ask", text="Gõ mã gửi hàng", key="tracking")]
    return _after_tracking(ctx, order, code)


async def quick_from_photo(ctx: Ctx, img: Image) -> list[dict]:
    """Một ảnh + lời người bán -> phiếu gần đủ, giá đề xuất, ảnh bìa; rồi đọc lại từng thông tin như thường."""
    db, s = ctx.db, ctx.s
    issue = vision.issue_from(vision.quality_metrics(img.path))
    if issue:   # vẫn chờ ảnh, chụp lại
        return [ctx.say(f"photo_guide_{issue}"), open_camera("listing", _guide_short(issue))]
    words = " ".join(t_ for ts, t_ in s.heard if (s.quick_since - ts).total_seconds() < 120)
    s.quick_since = None
    from app.services import notifier
    await notifier.push(ctx.seller.id, [
        {"type": "listing_live", "listing_id": 0, "title": "Đang xem ảnh…", "status": "drafting", "fields": [],
         "images": [f"/api/images/{img.id}/file"]},
        speak("Ảnh rõ rồi. Tôi đang xem ảnh và điền thông tin, chờ tôi vài giây nhé.")])
    out = await shopmaker.draft_from_photo(db, ctx.seller, img, words)
    if not out:
        return [{"type": "listing_live", "listing_id": 0, "title": "", "status": "cancelled", "fields": [], "images": []},
                speak(f"Tôi chưa nhận ra món hàng trong ảnh. {cap(ctx.h)} nói giúp tôi đang bán gì nhé."),
                card(**categories_card())]
    lst = out["listing"]
    s.active_listing_id, s.photo_attempts = lst.id, 0
    intro = f"Tôi xem ảnh rồi: {(img.description or '').rstrip('.')}. " if img.description else ""
    if out["filled"]:
        intro += f"Tôi đã điền sẵn {numbers.number_to_words(len(out['filled']))} thông tin, giờ đọc lại từng cái để {ctx.h} kiểm tra."
    p = out["price"]
    if p:
        intro += (f" Hàng giống thế này trên sàn bán khoảng {tp.money_short(p['min'])} đến {tp.money_short(p['max'])}. "
                  f"{cap(ctx.h)} nói không dưới {tp.money_short(p['floor'])}, nên tôi đề xuất {tp.money_short(p['price'])}.")
    return [speak(intro.strip())] + await continue_listing(ctx, lst)


def _after_tracking(ctx: Ctx, order: Order, code: str) -> list[dict]:
    osv.set_tracking(ctx.db, order, code)
    pre = [ctx.say("receipt_read", spoken=tp.tracking_spoken(code))]
    r = osv.request_action(ctx.db, ctx.seller, order, "mark_shipped")
    if not r["ok"]:
        return pre + [speak(r["say"])]
    return pre + ask_confirmation(ctx, r["confirmation"])


def _guide_short(issue: str) -> str:
    return {"dark": "Ra chỗ sáng hơn", "blurry": "Giữ yên tay", "cut_off": "Lùi ra xa một chút",
            "cluttered": "Dọn bớt đồ xung quanh"}.get(issue, "Chụp lại")


def _describe_photo(ctx: Ctx, img: Image) -> list[dict]:
    desc = (img.description or "").strip().rstrip(".")
    desc = desc[:1].lower() + desc[1:] if desc else None
    prompt = t("photo_describe", ctx.h, desc=desc) if desc else t("photo_describe_unknown", ctx.h)
    req = ConfirmationRequest(seller_id=ctx.seller.id, subject_ref=f"image:{img.id}:describe", kind="action", risk=Risk.YELLOW,
                              prompt_text=prompt, card={"kind": "photo", "image_id": img.id, "text": "Đúng hàng của bạn?",
                                                         "big": "📷", "detail": desc})
    return ask_confirmation(ctx, req)


def _order_for_photo(ctx: Ctx) -> Order | None:
    if ctx.s.active_order_id:
        o = ctx.db.get(Order, ctx.s.active_order_id)
        if o and o.status in osv.OPEN:
            return o
    return osv.find(ctx.db, ctx.seller, "latest")


# =====================================================================
# Bộ định tuyến luật (chạy được không cần mạng)
# =====================================================================

_SELL = re.compile(r"\b(bán|đăng)\b")


def _current_order(ctx: Ctx, statuses: tuple) -> Order | None:
    if ctx.s.active_order_id:
        o = ctx.db.get(Order, ctx.s.active_order_id)
        if o and o.status in statuses:
            return o
    return ctx.db.exec(select(Order).where(Order.seller_id == ctx.seller.id, Order.status.in_(statuses))
                       .order_by(Order.created_at.desc(), Order.id.desc())).first()


async def start_new_listing(ctx: Ctx, category: str, text: str = "") -> list[dict]:
    lst = ls.start_listing(ctx.db, ctx.seller, category)
    ctx.s.active_listing_id = lst.id
    ctx.s.photo_attempts = 0
    pre = [ctx.say("start_listing", label=catalog.category(category)["label"].lower())]
    name = ls.name_from_utterance(text) if text else ""
    if name and len(name) > 1:
        ls.set_field(ctx.db, ctx.seller, lst, "name", name, confidence=ctx.confidence)
        if numbers.parse(text, "price"):
            ls.set_field(ctx.db, ctx.seller, lst, "price", text, confidence=ctx.confidence)
    return pre + await continue_listing(ctx, lst)


async def order_action(ctx: Ctx, order: Order | None, action: str, reason: str | None = None) -> list[dict]:
    if not order:
        return [ctx.say("order_none")]
    ctx.s.active_order_id = order.id
    r = osv.request_action(ctx.db, ctx.seller, order, action, reason)
    if r["ok"]:
        req = r["confirmation"]
        # "nhận đơn" khi câu ngay trước đã đọc đủ chi tiết đơn -> chấp nhận luôn (mục 11.2)
        if action == "accept" and ctx.s.order_details_read == order.id and req.action_phrase in norm(ctx.text):
            log_confirmation(ctx.db, req, "confirmed", ctx.text, ctx.latency_ms)
            ctx.s.order_details_read = None
            return await apply_confirmed(ctx, req)
        return ask_confirmation(ctx, req)
    data = r["data"]
    ev = [speak(r["say"])]
    if data.get("need_reason"):
        ctx.s.awaiting = ("cancel_reason", order.id)
        ev.append(card(kind="choices", text="Vì sao hủy?", options=data["options"]))
    elif data.get("code") == "PACKING_NOT_VERIFIED":
        ev.append(open_camera("packing_check", "Bày đủ hàng của đơn lên bàn", order.id))
    elif data.get("code") == "NO_TRACKING":
        ctx.s.awaiting = ("photo", "receipt", order.id)
        ev.append(open_camera("receipt", "Chụp tờ biên nhận", order.id))
    return ev


def _reason_from(text: str) -> str | None:
    if has(text, "hết hàng", "hết rồi", "không còn"):
        return CANCEL_REASONS[0]
    if has(text, "khách yêu cầu", "khách bảo", "khách muốn hủy", "khách hủy"):
        return CANCEL_REASONS[1]
    if has(text, "không kịp", "không gửi kịp", "trễ"):
        return CANCEL_REASONS[2]
    m = re.match(r"^(?:số |thẻ )?(\d)$", text.strip())
    if m and 1 <= int(m.group(1)) <= 3:
        return CANCEL_REASONS[int(m.group(1)) - 1]
    return None


def _yes(text: str) -> bool:
    return has(f" {text} ", " có ", " làm ", "đồng ý", " ừ", " được", "làm đi", " vâng", " ok", " nghe", "đúng")


def _no(text: str) -> bool:
    return has(f" {text} ", " không ", " thôi", " chưa ", " khỏi")


async def next_task(ctx: Ctx, greet: bool = False) -> list[dict]:
    """Chủ động dẫn người bán tới việc quan trọng nhất đang chờ (không cần nhìn màn hình)."""
    db, s, h = ctx.db, ctx.s, ctx.h
    pre = f"Chào {h} {ctx.seller.name.split()[-1]}. " if greet else ""
    if s.pending:
        return _reask(ctx, s.pending, (pre + "Mình đang dở một việc.").strip())
    opens = osv.open_orders(db, ctx.seller.id)
    new = sorted([o for o in opens if o.status == "new"], key=lambda o: o.created_at)
    if new:
        o = new[0]
        s.active_order_id = s.order_details_read = o.id
        more = f"{cap(h)} có {numbers.number_to_words(len(new))} đơn mới. " if len(new) > 1 else ""
        text = pre + more + t("new_order", h, buyer=o.buyer_name, province=o.buyer_province, items=osv.items_spoken(db, o),
                                payout=tp.money_spoken(o.seller_payout), deadline=tp.deadline_spoken(o.ship_by))
        return [speak(text), card(**osv.order_card(db, o))]
    to_pack = [o for o in opens if o.status == "accepted"]
    if to_pack:
        o = to_pack[0]
        s.active_order_id = o.id
        s.awaiting = ("photo", "packing_check", o.id)
        text = (pre + f"Đơn của {o.buyer_name} cần {osv.items_spoken(db, o)}, hạn gửi {tp.deadline_spoken(o.ship_by)}. "
                f"{cap(h)} bày hàng lên bàn rồi nói 'chụp' để tôi kiểm tra nhé.")
        return [speak(text), card(**osv.order_card(db, o)), open_camera("packing_check", "Bày đủ hàng của đơn lên bàn", o.id)]
    to_ship = [o for o in opens if o.status == "packed"]
    if to_ship:
        o = to_ship[0]
        s.active_order_id = o.id
        s.awaiting = ("photo", "receipt", o.id)
        text = pre + f"Đơn của {o.buyer_name} đã đóng gói, hạn gửi {tp.deadline_spoken(o.ship_by)}. Gửi ở bưu cục xong, {h} nói 'chụp biên nhận' nhé."
        return [speak(text), card(**osv.order_card(db, o))]
    if support.waiting(db, ctx.seller.id):
        ev = await next_buyer_question(ctx)
        if pre and ev and ev[0].get("type") == "speak":
            ev[0]["text"] = pre + ev[0]["text"]
        return ev
    lst = ls.active_listing(db, ctx.seller.id)
    if lst:
        return [speak(pre + f"{cap(h)} đang đăng dở {ls.name_of(db, lst).lower()}. Mình làm tiếp nhé.")] + await continue_listing(ctx, lst)
    return [speak(pre + f"Hôm nay không còn việc gì gấp. {cap(h)} muốn bán hàng mới, hay nghe bản tin hôm nay?")]


async def show_briefing(ctx: Ctx) -> list[dict]:
    r = growth.daily_briefing(ctx.db, ctx.seller)
    if r["data"].get("suggestion_id"):
        ctx.s.awaiting = ("growth", r["data"]["suggestion_id"])
    return [speak(r["say"])] + r["events"]


async def growth_decision(ctx: Ctx, sid: int, decision: str) -> list[dict]:
    sug = ctx.db.get(GrowthSuggestion, sid)
    r = growth.respond(ctx.db, ctx.seller, sug, decision)
    if r["confirmation"]:
        return ask_confirmation(ctx, r["confirmation"])
    nxt = r["data"].get("next")
    if nxt:
        ctx.s.awaiting = tuple(nxt)
        if nxt[0] == "seller_reply":
            ctx.s.active_message_id = nxt[1]
    return [speak(r["say"])] + r["events"]


async def next_buyer_question(ctx: Ctx) -> list[dict]:
    ws = support.waiting(ctx.db, ctx.seller.id)
    if not ws:
        return [ctx.say("no_buyer_questions")]
    msg = ws[0]
    ctx.s.active_message_id = msg.id
    ctx.s.awaiting = ("seller_reply", msg.id)
    r = support.question_prompt(ctx.seller, msg)
    return [speak(r["say"])] + r["events"]


async def handle_awaiting(ctx: Ctx, text: str) -> list[dict] | None:
    """Trả None nếu câu nói không phải câu trả lời cho điều đang chờ."""
    aw = ctx.s.awaiting
    if not aw:
        return None
    kind = aw[0]
    db = ctx.db
    if kind == "field":
        _, lid, key = aw
        lst = db.get(Listing, lid)
        if has(text, "bỏ qua", "không biết") and ls.skip_field(db, lst, key):
            ctx.s.awaiting = None
            return [ctx.say("skip_ok")] + await continue_listing(ctx, lst)
        if has(text, "không biết"):
            return [speak(f"Phần này cần cho tin đăng. {cap(ctx.h)} hỏi người nhà rồi nói tôi nhé.")]
        r = ls.set_field(db, ctx.seller, lst, key, ctx.text, confidence=ctx.confidence)
        if not r["ok"]:
            return [speak(r["say"])]
        ctx.s.awaiting = None
        if r["confirmation"]:
            return ask_confirmation(ctx, r["confirmation"])
        return await continue_listing(ctx, lst)
    if kind == "wrong_which":
        lst = db.get(Listing, aw[1])
        options = {"tên": "name", "giá": "price", "số lượng": "stock", "bao nhiêu": "stock"}
        for tpl in catalog.category(lst.category)["fields"]:
            options[tpl["label"]] = tpl["key"]
        key = next((v for k, v in sorted(options.items(), key=lambda kv: -len(kv[0])) if k in text), None)
        if not key:
            return [ctx.say("summary_rejected", options="tên, giá hay số lượng")]
        f = ls.fields(db, lst.id)[key]
        f.state = FieldState.EMPTY if f.risk != Risk.GREEN else f.state
        db.add(f)
        lst.draft_raw = None
        db.add(lst)
        db.commit()
        ctx.s.awaiting = ("field", lst.id, key)
        return [ctx.say("field_rejected", label=ls.label_of(lst, key))]
    if kind == "cancel_reason":
        reason = _reason_from(text)
        if not reason:
            return [ctx.say("cancel_ask_reason", options="hết hàng, khách yêu cầu, hay không gửi kịp")]
        ctx.s.awaiting = None
        return await order_action(ctx, db.get(Order, aw[1]), "cancel", reason)
    if kind == "tracking":
        code = vision.tracking_from_text(ctx.text)
        if not code:
            return [ctx.say("receipt_unsure")]
        ctx.s.awaiting = None
        return _after_tracking(ctx, db.get(Order, aw[1]), code)
    if kind == "seller_reply":
        if has(text, "để sau", "không biết", "chưa trả lời"):
            ctx.s.awaiting = None
            return [speak("Vâng, để sau ạ. Khách vẫn đang chờ.")]
        msg = db.get(BuyerMessage, aw[1])
        r = await support.seller_answer(db, ctx.seller, msg, ctx.text)
        return ask_confirmation(ctx, r["confirmation"]) if r["confirmation"] else [speak(r["say"])]
    if kind == "restock":
        lst = db.get(Listing, aw[1])
        raw = ctx.text
        p = numbers.parse(raw, "stock")
        if p and has(text, "thêm"):
            raw = str((lst.stock or 0) + p.int_value)
        r = ls.request_stock_update(db, ctx.seller, lst, raw)
        if not r["ok"]:
            return [speak(r["say"])]
        ctx.s.awaiting = None
        return ask_confirmation(ctx, r["confirmation"])
    if kind == "growth":
        if has(text, "để sau", "lúc khác"):
            ctx.s.awaiting = None
            return await growth_decision(ctx, aw[1], "later")
        if _no(text):
            ctx.s.awaiting = None
            return await growth_decision(ctx, aw[1], "decline")
        if _yes(text):
            ctx.s.awaiting = None
            return await growth_decision(ctx, aw[1], "accept")
        return None
    if kind == "photo":
        if has(text, "chụp", "camera", "máy ảnh"):
            purpose, ref = aw[1], aw[2]
            return [speak("Vâng, nhấn nút chụp nhé."), open_camera(purpose, "Chụp ảnh", ref)]
        return None
    return None


async def route_rules(ctx: Ctx) -> list[dict]:
    db, s = ctx.db, ctx.s
    text = norm(ctx.text)

    if not text:
        return [ctx.say("greeting_back")]

    # điều khiển hội thoại (trước mọi thứ)
    if text in ("nói lại", "nhắc lại", "nói lại đi"):
        return s.last_events or [ctx.say("nothing_to_repeat")]
    if has(text, "chậm thôi", "nói chậm"):
        ctx.seller.tts_speed = round(max(0.6, ctx.seller.tts_speed - 0.1), 2)
        db.add(ctx.seller)
        db.commit()
        return [ctx.say("slower_ok")] + [e for e in s.last_events if e.get("type") == "speak"][:1]
    if text in ("dừng", "dừng lại"):
        s.awaiting = None
        return [ctx.say("stopped")]
    if has(text, "rút lại", "thôi không đăng", "không đăng nữa"):
        r = ls.undo(db, ctx.seller)
        return [speak(r["say"])]

    if has(text, "việc tiếp", "làm gì tiếp", "còn việc gì", "làm gì bây giờ", "giờ làm gì"):
        return await next_task(ctx)

    # đơn hàng
    if has(text, "nhận đơn"):
        return await order_action(ctx, _current_order(ctx, ("new",)), "accept")
    if has(text, "đã gửi rồi", "gửi rồi", "đã gửi hàng", "gửi xong"):
        return await order_action(ctx, _current_order(ctx, ("packed", "accepted")), "mark_shipped")
    if has(text, "bỏ qua kiểm tra"):
        return await order_action(ctx, _current_order(ctx, ("accepted",)), "packing_override")
    if has(text, "đóng gói xong", "đã đóng gói", "gói xong"):
        return await order_action(ctx, _current_order(ctx, ("accepted",)), "mark_packed")
    if has(text, "kiểm tra hàng", "chụp hàng", "kiểm tra đơn", "xem hàng"):
        o = _current_order(ctx, ("accepted",))
        if not o:
            return [ctx.say("order_none")]
        s.active_order_id = o.id
        return [ctx.say("packing_ask_photo"), open_camera("packing_check", "Bày đủ hàng của đơn lên bàn", o.id)]
    if has(text, "biên nhận", "mã gửi hàng", "mã vận đơn"):
        o = _current_order(ctx, ("packed",))
        if not o:
            return [ctx.say("order_none")]
        s.active_order_id = o.id
        return [ctx.say("receipt_ask_photo"), open_camera("receipt", "Chụp tờ biên nhận", o.id)]
    if has(text, "hủy đơn"):
        o = _current_order(ctx, ("new", "accepted"))
        return await order_action(ctx, o, "cancel", _reason_from(text))
    if has(text, "sắp trễ", "gần hạn", "sắp hết hạn", "trễ hạn"):
        return [speak(osv.list_orders(db, ctx.seller, "due_soon")["say"])]
    if has(text, "bưu cục", "lịch gửi", "đi gửi hàng", "ngày nào gửi", "gom đơn"):
        return [speak(osv.plan_shipping_trip(db, ctx.seller)["say"])]
    if has(text, "tháng này", "tiền về", "được bao nhiêu tiền"):
        return [speak(osv.month_payout(db, ctx.seller))]
    if has(text, "đọc đơn", "đơn mới nhất", "đơn của", "xem đơn", "đơn mới"):
        m = re.search(r"đơn của (?:chị |anh |cô |bác |em |ông |bà )?(.+)", text)
        o = osv.find(db, ctx.seller, m.group(1).split(" ở ")[0] if m else "latest")
        if not o:
            return [ctx.say("order_not_found")]
        s.active_order_id = o.id
        s.order_details_read = o.id
        ev = [speak(osv.order_detail(db, ctx.seller, o)), card(**osv.order_card(db, o))]
        if o.status == "new":
            ev[0]["text"] += f" {cap(ctx.h)} muốn nhận đơn thì nói 'nhận đơn'."
        return ev
    if has(text, "mấy đơn", "có đơn", "đơn nào", "bao nhiêu đơn", "đơn hàng", "đơn hôm nay"):
        return [speak(osv.list_orders(db, ctx.seller, "today")["say"])]

    # trực shop
    if has(text, "bảo khách", "trả lời khách là", "nói với khách") and s.active_message_id:
        msg = db.get(BuyerMessage, s.active_message_id)
        r = await support.seller_answer(db, ctx.seller, msg, ctx.text)
        return ask_confirmation(ctx, r["confirmation"]) if r["confirmation"] else [speak(r["say"])]
    if has(text, "khách hỏi", "câu hỏi", "trả lời khách", "tin nhắn", "khách nhắn", "có khách"):
        return await next_buyer_question(ctx)

    # phát triển, bản tin
    if has(text, "bản tin", "hôm nay thế nào", "tổng kết", "tin hôm nay", "hôm nay bán"):
        return await show_briefing(ctx)
    if has(text, "bán được nhiều", "bán nhiều hơn", "gợi ý", "làm sao bán", "tăng đơn"):
        sug = growth.get_suggestion(db, ctx.seller)
        r = growth.suggestion_res(ctx.seller, sug)
        if sug:
            s.awaiting = ("growth", sug.id)
        return [speak(r["say"])] + r["events"]

    # tồn kho
    m_stock = re.search(r"\b(còn|có thêm|thêm|nhập thêm|cập nhật)\b.*\b(chai|gói|hũ|cái|lọ|hộp)\b", text)
    if m_stock and numbers.parse(text, "stock") and not (s.awaiting and s.awaiting[0] == "field"):
        lst = ls.find_by_name(db, ctx.seller.id, text) or (db.get(Listing, s.active_listing_id) if s.active_listing_id else None)
        if lst and lst.status in ("published", "hidden", "pending_publish"):
            raw = ctx.text
            p = numbers.parse(text, "stock")
            if has(text, "thêm"):
                raw = str((lst.stock or 0) + p.int_value)
            r = ls.request_stock_update(db, ctx.seller, lst, raw)
            return ask_confirmation(ctx, r["confirmation"]) if r["confirmation"] else [speak(r["say"])]

    # đổi giá
    m_price = re.search(r"đổi giá (.*?)(?:thành|còn|lên|xuống) (.+)$", text)
    if m_price:
        lst = ls.find_by_name(db, ctx.seller.id, m_price.group(1)) or ls.active_listing(db, ctx.seller.id)
        if not lst:
            return [ctx.say("not_understood")]
        if lst.status in ("drafting", "ready"):
            r = ls.set_field(db, ctx.seller, lst, "price", m_price.group(2), confidence=ctx.confidence, is_correction=True)
            return ask_confirmation(ctx, r["confirmation"]) if r["confirmation"] else [speak(r["say"])]
        r = ls.request_price_change(db, ctx.seller, lst, m_price.group(2))
        return ask_confirmation(ctx, r["confirmation"]) if r["confirmation"] else [speak(r["say"])]

    # đổi chế độ
    if has(text, "chế độ bấm", "đổi sang bấm", "không nghe được", "chế độ chạm") or (has(text, "chế độ nói", "đổi sang nói")):
        mode = "touch" if has(text, "bấm", "chạm", "không nghe") else "voice"
        return ask_confirmation(ctx, mode_request(ctx, mode))

    # "làm tiếp" là lệnh, không phải câu trả lời cho trường đang hỏi
    if text in ("làm tiếp", "tiếp tục", "tiếp đi", "làm tiếp đi", "đăng đi"):
        lst = db.get(Listing, s.active_listing_id) if s.active_listing_id else ls.active_listing(db, ctx.seller.id)
        if lst and lst.status in ("drafting", "ready"):
            s.awaiting = None
            return await continue_listing(ctx, lst)

    # việc đang chờ (trả lời câu hỏi của agent)
    out = await handle_awaiting(ctx, text)
    if out is not None:
        return out

    # đăng hàng
    cat = catalog.detect_category(text)
    if cat and (_SELL.search(text) or has(text, "muốn")):
        return await start_new_listing(ctx, cat, ctx.text)
    if has(text, "đăng đi", "làm tiếp", "tiếp tục", "tiếp đi"):
        lst = db.get(Listing, s.active_listing_id) if s.active_listing_id else ls.active_listing(db, ctx.seller.id)
        if lst and lst.status in ("drafting", "ready"):
            return await continue_listing(ctx, lst)
    if _SELL.search(text) or has(text, "sản phẩm mới", "hàng mới"):
        s.awaiting = ("category",)
        return [ctx.say("ask_category"), categories_card()]
    if s.awaiting and s.awaiting[0] == "category" and cat:
        return await start_new_listing(ctx, cat)
    if has(text, "chào", "bắt đầu", "xin chào", "alo"):
        return [ctx.say("greeting_back")]
    return [ctx.say("not_understood")]


def categories_card() -> dict:
    return card(kind="categories", text="Bán loại gì?",
                options=[{"value": k, "label": v["label"], "visual": v.get("visual")} for k, v in catalog.categories().items()])


def mode_request(ctx: Ctx, mode: str) -> ConfirmationRequest:
    return ConfirmationRequest(seller_id=ctx.seller.id, subject_ref=f"seller:{ctx.seller.id}:mode", kind="action", risk=Risk.YELLOW,
                               prompt_text=t("ask_change_mode", ctx.h, mode_label=MODE_LABEL[mode]), action_phrase="đổi",
                               card={"kind": "confirm", "big": "👂" if mode == "voice" else "👆", "text": f"Đổi sang chế độ {MODE_LABEL[mode]}"},
                               payload={"mode": mode})


async def route_button(ctx: Ctx) -> list[dict]:
    db, s, b = ctx.db, ctx.s, ctx.button or ""
    if b in ("repeat",):
        return s.last_events or [ctx.say("nothing_to_repeat")]
    if b == "slower":
        ctx.text = "chậm thôi"
        return await route_rules(ctx)
    if b in ("timeout", "yes_hold", "no", "stop"):
        return []
    if b in ("hello", "next_task"):
        return await next_task(ctx, greet=b == "hello")
    if b == "card:new_listing":
        s.awaiting = ("category",)
        return [ctx.say("ask_category"), categories_card()]
    if b.startswith("cat:"):
        return await start_new_listing(ctx, b[4:])
    if b == "card:orders":
        r = osv.list_orders(db, ctx.seller, "all_open")
        ev = [speak(r["say"])]
        for oid in r["data"].get("order_ids", [])[:6]:
            ev.append(card(**osv.order_card(db, db.get(Order, oid))))
        return ev
    if b == "card:questions":
        return await next_buyer_question(ctx)
    if b == "card:today":
        return await show_briefing(ctx)
    if b == "undo":
        return [speak(ls.undo(db, ctx.seller)["say"])]
    if b == "skip" and s.awaiting and s.awaiting[0] == "field":
        ctx.text = "bỏ qua"
        return await handle_awaiting(ctx, "bỏ qua") or []
    if b.startswith("order:"):
        _, oid, action = b.split(":")
        order = db.get(Order, int(oid))
        s.active_order_id = order.id
        if action == "packing_check":
            return [ctx.say("packing_ask_photo"), open_camera("packing_check", "Bày đủ hàng của đơn lên bàn", order.id)]
        if action == "receipt":
            return [ctx.say("receipt_ask_photo"), open_camera("receipt", "Chụp tờ biên nhận", order.id)]
        return await order_action(ctx, order, action)
    if b.startswith("growth:"):
        _, sid, decision = b.split(":")
        s.awaiting = None
        return await growth_decision(ctx, int(sid), decision)
    if b.startswith("mode:"):
        return ask_confirmation(ctx, mode_request(ctx, b[5:]))
    if b.startswith("choice:"):
        ctx.text = b[7:]
        return await route_rules(ctx)
    return []
