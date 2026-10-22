"""Bộ máy xác nhận (mục 9). Câu trả lời đúng/sai được phân tích bằng code, LLM không tham gia."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlmodel import Session, select

from app.config import RUBBER_STAMP_MS
from app.models import BlockedError, ConfirmationLog, Risk
from app.validators import numbers

YES = {"đúng", "đúng rồi", "phải", "chuẩn", "ừ đúng", "vâng đúng", "đúng ạ", "chính xác", "đồng ý", "ok đúng"}
NO = {"sai", "không", "không phải", "sai rồi", "chưa đúng", "nhầm", "không đúng"}
NO_SHORT = {"thôi", "thôi khỏi", "thôi bỏ", "chưa", "hủy"}   # chỉ tính khi cả câu chỉ có vậy
WEAK_YES = {"ừ", "ờ", "vâng", "ok", "ừm", "dạ", "được", "ờ ờ", "ừ ừ", "uh", "ừa"}
CONTROL = {"nói lại": "repeat", "nhắc lại": "repeat", "chậm thôi": "slower", "nói chậm thôi": "slower",
           "nói chậm": "slower", "dừng": "stop", "dừng lại": "stop"}
_PARTICLES = {"ạ", "à", "nhé", "nha", "đi", "cơ", "mà", "ơi"}


@dataclass
class ConfirmationRequest:
    seller_id: int
    subject_ref: str                  # "listing:12:price" | "order:5:accept" | "listing:12:publish"
    kind: str                         # "field" | "action"
    risk: Risk
    prompt_text: str
    value_display: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    two_step: bool = False
    action_phrase: str | None = None
    card: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)
    open_question: str | None = None  # câu hỏi mở khi nghi gật đầu theo quán tính
    attempts: int = 0
    timeouts: int = 0
    asked_at: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    @property
    def number(self):
        return self.value_display.get("number")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk"] = self.risk.value
        d["asked_at"] = self.asked_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ConfirmationRequest":
        d = dict(d)
        d["risk"] = Risk(d["risk"])
        d["asked_at"] = datetime.fromisoformat(d["asked_at"])
        return cls(**d)


@dataclass
class Resolution:
    kind: str                         # confirmed | rejected | corrected | clarify | control
    reason: str | None = None         # explicit_yes | unclear | say_action_phrase
    new_value: numbers.ParsedNumber | None = None
    control: str | None = None


def normalize(text: str | None) -> str:
    return numbers.normalize_text(text or "")


def _has(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def _strip_particles(text: str) -> str:
    return " ".join(w for w in text.split() if w not in _PARTICLES)


def resolve(req: ConfirmationRequest, text: str | None, button: str | None = None) -> Resolution:
    if button == "yes_hold":
        return Resolution("confirmed")
    if button == "no":
        return Resolution("rejected")
    if button in ("repeat", "slower", "stop"):
        return Resolution("control", control=button)

    t = normalize(text)
    bare = _strip_particles(t)
    if t in CONTROL or bare in CONTROL:
        return Resolution("control", control=CONTROL.get(t) or CONTROL[bare])
    says_no = any(_has(t, p) for p in NO) or bare in NO_SHORT

    # 1. Có số mới -> người bán đang sửa giá trị
    if req.number is not None:
        parsed = numbers.parse(t, context=req.value_display.get("key") or req.subject_ref)
        if parsed:
            if parsed.int_value != int(req.number):
                return Resolution("corrected", new_value=parsed)
            if says_no:                           # "không phải bảy trăm"
                return Resolution("rejected")
            if req.open_question or not req.two_step:
                return Resolution("confirmed")   # nói lại đúng con số = xác nhận rõ ràng
    if says_no:
        return Resolution("rejected")
    if req.open_question:
        return Resolution("clarify", reason="open_question")

    # 2. Hai bước: phải đúng cụm từ hành động
    if req.two_step:
        if req.action_phrase and _has(t, req.action_phrase):
            return Resolution("confirmed")
        return Resolution("clarify", reason="say_action_phrase")

    if req.action_phrase and _has(t, req.action_phrase):
        return Resolution("confirmed")

    # 3. RED: "ừ" yếu lần đầu -> hỏi lại rõ hơn
    weak = t in WEAK_YES or bare in WEAK_YES
    if req.risk == Risk.RED and weak and req.attempts == 0:
        return Resolution("clarify", reason="explicit_yes")
    if any(_has(t, p) for p in YES) or (weak and (req.risk != Risk.RED or req.attempts > 0)):
        return Resolution("confirmed")
    return Resolution("clarify", reason="unclear")


# ---------- nhật ký & chống gật đầu theo quán tính ----------

def log_confirmation(db: Session, req: ConfirmationRequest, result: str, response_text: str | None,
                     response_ms: int | None) -> None:
    db.add(ConfirmationLog(seller_id=req.seller_id, subject_type=req.kind, subject_ref=req.subject_ref,
                           risk=req.risk.value, prompt_text=req.prompt_text, response_text=response_text,
                           response_ms=response_ms, result=result, layer_flags=list(req.flags)))
    db.commit()


def log_blocked(db: Session, seller_id: int, layer: int, code: str, detail: str) -> None:
    db.add(BlockedError(seller_id=seller_id, layer=layer, code=code, detail=str(detail)[:500]))
    db.commit()


def recent_confirmations(db: Session, seller_id: int, n: int = 3) -> list[ConfirmationLog]:
    return list(db.exec(select(ConfirmationLog).where(ConfirmationLog.seller_id == seller_id)
                        .order_by(ConfirmationLog.id.desc()).limit(n)).all())


def rubber_stamp_suspected(db: Session, seller_id: int, threshold_ms: float = RUBBER_STAMP_MS) -> bool:
    last = recent_confirmations(db, seller_id, 3)
    return (len(last) == 3
            and all(c.result == "confirmed" and c.risk == "red" for c in last)
            and all(c.response_ms is not None and c.response_ms < threshold_ms for c in last))


def needs_open_question(db: Session, req: ConfirmationRequest) -> bool:
    """Chỉ hỏi mở với trường số RED (giá, dung tích, số lượng...) chưa từng hỏi mở."""
    return (req.kind == "field" and req.risk == Risk.RED and req.number is not None
            and not req.open_question and rubber_stamp_suspected(db, req.seller_id))
