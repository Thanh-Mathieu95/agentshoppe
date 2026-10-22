"""Nhận dạng giọng nói phía server (OpenAI). Không bật thì trình duyệt tự nhận dạng (Web Speech, vi-VN)."""
from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass, field

from app import config

log = logging.getLogger(__name__)

# Gợi ý từ vựng: giúp mô hình nghe đúng số và từ bán hàng ("đăng đi" chứ không phải "đan đi").
PROMPT = ("Người bán hàng vùng cao nói tiếng Việt về sản phẩm, giá tiền và đơn hàng. Ghi số bằng chữ như người nói, "
          "không đổi sang chữ số. Từ hay gặp: mật ong, chè Shan tuyết, thổ cẩm, gác bếp, nghìn, triệu, củ, rưỡi, mốt, lăm, "
          "nửa lít, lạng, cân, chai, hũ, gói, đăng đi, rút lại, nhận đơn, đã gửi rồi, đóng gói xong, hủy đơn, gửi đi, "
          "nói lại, chậm thôi, đúng, sai, bỏ qua.")


@dataclass
class Transcript:
    text: str
    confidence: float | None = None
    words: list[dict] = field(default_factory=list)


def enabled() -> bool:
    return config.STT_PROVIDER == "openai" and bool(config.OPENAI_API_KEY)


async def transcribe(audio: bytes, filename: str = "speech.webm", prompt: str = PROMPT) -> Transcript:
    if not enabled():
        return Transcript(text="")
    from app.agent.llm import client

    def file():
        f = io.BytesIO(audio)
        f.name = filename
        return f

    base = {"model": config.STT_MODEL, "language": "vi", "prompt": prompt}
    try:   # có logprobs -> độ tin cậy cho lớp chống nghe nhầm
        r = await client().audio.transcriptions.create(file=file(), include=["logprobs"], response_format="json", **base)
    except Exception as e:
        log.info("transcribe without logprobs: %s", str(e)[:120])
        r = await client().audio.transcriptions.create(file=file(), **base)
    conf = None
    logprobs = getattr(r, "logprobs", None)
    if logprobs:
        conf = round(sum(math.exp(lp.logprob) for lp in logprobs) / len(logprobs), 3)
    return Transcript(text=(r.text or "").strip(), confidence=conf)
