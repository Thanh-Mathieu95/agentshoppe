"""Trực shop: chỉ trả lời từ trường CONFIRMED / FAQ đã duyệt (mục 13)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app import catalog
from app.agent import llm
from app.confirm import templates as tp
from app.confirm.engine import ConfirmationRequest, log_blocked
from app.events import card, notify, res
from app.i18n.vi import t
from app.models import FAQ, BuyerMessage, FieldState, Listing, ListingField, Risk, Seller, Source
from app.services import listings as ls
from app.validators.numbers import normalize_text

# chủ đề câu hỏi -> trường dữ liệu trả lời được
TOPICS = [
    ("additives", ["pha đường", "pha thêm", "có đường", "nguyên chất", "pha trộn", "phụ gia"], "thành phần"),
    ("origin", ["ở đâu", "nguồn gốc", "lấy ở", "xuất xứ", "từ đâu", "hái ở", "làm ở"], "nơi lấy hàng"),
    ("volume_ml", ["bao nhiêu ml", "mấy ml", "dung tích", "mấy lít", "bao nhiêu lít", "chai bao nhiêu"], "dung tích"),
    ("weight_g", ["nặng", "mấy lạng", "bao nhiêu gam", "khối lượng"], "khối lượng"),
    ("price", ["giá", "bao nhiêu tiền", "nhiêu tiền"], "giá"),
    ("container", ["thủy tinh", "chai nhựa", "chai gì", "đựng"], "loại chai"),
    ("harvest_time", ["tháng nào", "thu hoạch", "lấy khi nào", "hái khi nào", "mùa nào", "mới không"], "thời gian lấy"),
    ("storage", ["bảo quản", "để tủ lạnh", "để được bao lâu"], "cách bảo quản"),
    ("stock", ["còn hàng", "còn không", "hết hàng"], "còn hàng"),
    ("processing", ["sao tay", "sao máy"], "cách sao"),
    ("material", ["chất liệu", "vải gì", "làm bằng"], "chất liệu"),
]

SCAM_PATTERNS = [r"chuyển khoản (trước|ngoài|qua zalo)", r"\botp\b", r"mã (xác nhận|xác thực)", r"gửi hàng trước",
                 r"qua zalo", r"https?://", r"bit\.ly", r"đã chuyển tiền", r"ngoài (sàn|shopee)", r"liên hệ zalo"]


def topic_of(text: str) -> tuple[str, str] | None:
    low = normalize_text(text)
    for key, kws, label in TOPICS:
        if any(k in low for k in kws):
            return key, label
    return None


def is_scam(text: str) -> bool:
    low = text.lower()
    return any(re.search(p, low) for p in SCAM_PATTERNS)


_STOP = {"có", "không", "shop", "ơi", "vậy", "ạ", "à", "là", "này", "thế", "nào", "bạn", "cho", "hỏi", "với", "nhé", "của", "em", "chị", "anh"}


def _faq_match(db: Session, listing: Listing, text: str) -> FAQ | None:
    # Tên sản phẩm có ở mọi câu hỏi nên không được tính là bằng chứng khớp.
    name_words = set(normalize_text(ls.name_of(db, listing) + " " + " ".join(catalog.category(listing.category)["keywords"])).split())
    words = set(normalize_text(text).split()) - _STOP - name_words
    if not words:
        return None
    best, score = None, 0.0
    for f in db.exec(select(FAQ).where(FAQ.listing_id == listing.id, FAQ.approved_by_seller == True)).all():  # noqa: E712
        q = set(normalize_text(f.question).split()) - _STOP - name_words
        s = len(words & q) / len(words | q) if q else 0
        if s > score:
            best, score = f, s
    return best if score >= 0.6 else None


def _field_answer(listing: Listing, f: ListingField) -> str:
    k, v = f.key, f.value
    if k == "price":
        return f"Dạ, giá mỗi {ls.container(listing)} là {tp.money_digits(int(v))} ạ."
    if k == "volume_ml":
        return f"Dạ, mỗi {ls.container(listing)} {tp.volume_short(int(v))} ạ."
    if k == "weight_g":
        return f"Dạ, mỗi {ls.container(listing)} nặng {v} gam ạ."
    if k == "stock":
        return "Dạ, shop còn hàng ạ." if int(v) > 0 else "Dạ, shop tạm hết hàng ạ."
    if k == "origin":
        return f"Dạ, hàng lấy ở {v} ạ."
    if k == "harvest_time":
        return f"Dạ, hàng lấy vào {v} ạ."
    if k == "additives":
        return v if v.startswith("Dạ") else f"Dạ, {v[0].lower() + v[1:]} ạ."
    return f"Dạ, {ls.label_of(listing, k)}: {v} ạ."


def auto_answer(db: Session, msg: BuyerMessage) -> tuple[str, list[str]] | None:
    """Trả (câu trả lời, nguồn) hoặc None nếu không có nguồn đã xác nhận."""
    if not msg.listing_id:
        return None
    listing = db.get(Listing, msg.listing_id)
    faq = _faq_match(db, listing, msg.text)
    if faq:
        return faq.answer, [f"faq:{faq.id}"]
    tp_ = topic_of(msg.text)
    if tp_:
        f = ls.fields(db, listing.id).get(tp_[0])
        if f and f.state == FieldState.CONFIRMED and f.value:
            return _field_answer(listing, f), [f"field:{listing.id}:{f.key}"]
    return None


def valid_refs(db: Session, refs: list[str]) -> bool:
    if not refs:
        return False
    for r in refs:
        parts = r.split(":")
        if parts[0] == "faq":
            f = db.get(FAQ, int(parts[1]))
            if not f or not f.approved_by_seller:
                return False
        elif parts[0] == "field":
            f = ls.fields(db, int(parts[1])).get(parts[2])
            if not f or f.state != FieldState.CONFIRMED:
                return False
        else:
            return False
    return True


def answer_buyer(db: Session, msg: BuyerMessage, answer: str, refs: list[str]) -> dict:
    if not valid_refs(db, refs):
        return res(False, warnings=[{"code": "NO_SOURCE", "layer": 3, "params": {"refs": refs}}])
    msg.answer = answer
    msg.answer_sources = refs
    msg.status = "answered_auto"
    db.add(msg)
    db.commit()
    return res(True, data={"message_id": msg.id})


def ask_seller(db: Session, seller: Seller, msg: BuyerMessage) -> dict:
    msg.answer = t("buyer_wait", seller.honorific)
    msg.status = "waiting_seller"
    db.add(msg)
    db.commit()
    return res(True, data={"message_id": msg.id})


def ingest(db: Session, seller: Seller, msg: BuyerMessage) -> list[dict]:
    """Khách hỏi -> tự trả lời / cảnh báo lừa đảo / chuyển người bán. Trả sự kiện cho người bán."""
    h = seller.honorific
    if is_scam(msg.text):
        msg.status = "scam_flagged"
        db.add(msg)
        db.commit()
        log_blocked(db, seller.id, 3, "SCAM_MESSAGE", msg.text[:120])
        return [notify("warning", {"message_id": msg.id, "text": t("scam_warning", h)}, vibrate=[500, 200, 500, 200, 500]),
                {"type": "speak", "text": t("scam_warning", h), "priority": "confirm"},
                card(kind="warning", big="⚠", text="Tin lừa đảo. Đừng gửi hàng.", detail=msg.text)]
    ans = auto_answer(db, msg)
    if ans:
        answer_buyer(db, msg, ans[0], ans[1])
        topic = topic_of(msg.text)
        return [notify("buyer_question", {"message_id": msg.id, "auto": True,
                                          "text": t("auto_answered", h, topic=topic[1] if topic else "sản phẩm")}, vibrate=[100])]
    ask_seller(db, seller, msg)
    return [notify("buyer_question", {"message_id": msg.id, "auto": False, "text": t("buyer_question_queued", h)})]


def waiting(db: Session, seller_id: int) -> list[BuyerMessage]:
    return list(db.exec(select(BuyerMessage).where(BuyerMessage.seller_id == seller_id, BuyerMessage.status == "waiting_seller")
                        .order_by(BuyerMessage.created_at)).all())


def waiting_over(db: Session, seller_id: int, hours: int = 12) -> list[BuyerMessage]:
    cutoff = datetime.now() - timedelta(hours=hours)
    return [m for m in waiting(db, seller_id) if m.created_at <= cutoff]


def question_prompt(seller: Seller, msg: BuyerMessage) -> dict:
    text = t("buyer_question", seller.honorific, buyer=msg.buyer_name, text=msg.text)
    return res(True, say=text, data={"message_id": msg.id},
               events=[card(kind="question", big="?", text=msg.text, buyer=msg.buyer_name, message_id=msg.id)])


_PRONOUNS = [(r"\b(nhà (cô|tôi|mình|em))\b", "nhà shop"), (r"\b(cô|tôi|mình|em)\b", "shop")]


def polite_rules(raw: str) -> str:
    s = raw.strip().strip(".")
    s = re.sub(r"^(bảo (khách|họ)( là)?|nói (với )?(khách|họ)( là)?|trả lời( là)?)\s+", "", s, flags=re.I)
    for pat, rep in _PRONOUNS:
        s = re.sub(pat, rep, s, flags=re.I)
    return f"Dạ, {s[0].lower() + s[1:]} ạ." if s else ""


async def polite(raw: str, question: str) -> str:
    if llm.enabled():
        try:
            out = await llm.complete_text(
                "Viết lại câu trả lời của người bán thành MỘT câu lịch sự gửi khách mua hàng, bắt đầu bằng 'Dạ,'. "
                "Giữ nguyên nghĩa, không thêm thông tin mới, không hứa hẹn, dưới 30 từ. Chỉ trả về câu đó.",
                f"Khách hỏi: {question}\nNgười bán nói: {raw}")
            if out:
                return out.strip().strip('"')
        except Exception:
            pass
    return polite_rules(raw)


async def seller_answer(db: Session, seller: Seller, msg: BuyerMessage, raw: str) -> dict:
    answer = await polite(raw, msg.text)
    if not answer:
        return res(False, say="Tôi chưa nghe rõ câu trả lời ạ.")
    req = ConfirmationRequest(
        seller_id=seller.id, subject_ref=f"message:{msg.id}:reply", kind="action", risk=Risk.YELLOW,
        prompt_text=t("seller_answer_prompt", seller.honorific, answer=answer), action_phrase="gửi đi",
        card={"kind": "confirm", "big": "💬", "text": answer, "risk": "yellow", "question": msg.text},
        payload={"answer": answer, "raw": raw},
    )
    return res(True, confirmation=req)


def apply_reply(db: Session, seller: Seller, msg: BuyerMessage, answer: str, raw: str) -> str:
    msg.answer = answer
    msg.status = "answered_seller"
    msg.answer_sources = ["seller"]
    db.add(msg)
    if msg.listing_id:
        faq = FAQ(listing_id=msg.listing_id, question=normalize_text(msg.text), answer=answer, approved_by_seller=True)
        db.add(faq)
        topic = topic_of(msg.text)
        if topic:
            fs = ls.fields(db, msg.listing_id)
            if topic[0] not in fs or fs[topic[0]].state != FieldState.CONFIRMED:
                f = fs.get(topic[0]) or ListingField(listing_id=msg.listing_id, key=topic[0], risk=Risk.YELLOW)
                f.value = answer
                f.state = FieldState.CONFIRMED
                f.source = Source.VOICE
                f.raw_utterance = raw
                f.confirmed_at = datetime.now()
                db.add(f)
    db.commit()
    return t("seller_answer_sent", seller.honorific)
