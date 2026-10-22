"""Soát nguồn tin đăng: mỗi câu phải có thẻ [key] trỏ tới trường đã xác nhận (mục 9.8)."""
import re

from app.models import FieldState

BANNED_CLAIMS = ["nguyên chất", "100%", "chữa", "trị bệnh", "tốt nhất", "số 1", "cam kết", "thần dược"]
TAG = re.compile(r"\[([a-z_]+)\]")
LEAD_TAGS = re.compile(r"^(?:\[[a-z_]+\]\s*)+")
SYSTEM_KEYS = {"policy"}   # câu bắt buộc theo quy định ngành hàng, do hệ thống thêm


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", text or "") if p.strip()]
    out: list[str] = []
    for p in parts:
        lead = LEAD_TAGS.match(p)
        if out and lead:   # thẻ đứng đầu (sau dấu chấm câu trước) là nguồn của câu TRƯỚC
            out[-1] += " " + lead.group(0).strip()
            p = p[lead.end():].strip()
        if p and TAG.sub("", p).strip(" .") == "" and out:
            out[-1] += " " + p
        elif p:
            out.append(p)
    return out


def strip_tags(text: str) -> str:
    s = TAG.sub("", text or "")
    s = re.sub(r"\s+([.,!?])", r"\1", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def seller_said(fields: dict, claim: str) -> bool:
    claim = claim.lower()
    for f in fields.values():
        for said in [f.raw_utterance or "", *(f.history or [])]:
            if claim in said.lower():
                return True
    return False


def check(description_tagged: str, fields: dict) -> list[tuple[str, str]]:
    """fields: {key: ListingField}. Trả danh sách (mã lỗi, chi tiết)."""
    errors = []
    for sentence in split_sentences(description_tagged):
        keys = TAG.findall(sentence)
        if not keys:
            errors.append(("UNSOURCED_SENTENCE", sentence))
        for k in keys:
            if k in SYSTEM_KEYS:
                continue
            f = fields.get(k)
            if not f or f.state != FieldState.CONFIRMED:
                errors.append(("SOURCE_NOT_CONFIRMED", f"{k}: {sentence}"))
        low = sentence.lower()
        for claim in BANNED_CLAIMS:
            if claim in low and not seller_said(fields, claim):
                errors.append(("BANNED_CLAIM", claim))
    return errors


def clean(description_tagged: str, fields: dict) -> tuple[str, str]:
    """Bỏ câu lỗi. Trả (bản có thẻ, bản công khai không thẻ)."""
    kept = []
    for sentence in split_sentences(description_tagged):
        if not check(sentence, fields):
            kept.append(sentence)
    tagged = " ".join(kept)
    return tagged, strip_tags(tagged)
