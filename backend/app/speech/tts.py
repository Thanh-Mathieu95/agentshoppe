"""Đọc thành giọng phía server (tùy chọn). Mặc định trình duyệt đọc (speechSynthesis, vi-VN)."""
from app import config


def enabled() -> bool:
    return config.TTS_PROVIDER == "openai" and bool(config.OPENAI_API_KEY)


async def synthesize(text: str, speed: float = 1.0) -> bytes:
    from app.agent.llm import client
    r = await client().audio.speech.create(model=config.TTS_MODEL, voice=config.TTS_VOICE, input=text,
                                           speed=max(0.5, min(1.5, speed)), response_format="mp3",
                                           instructions="Giọng nữ miền Bắc, ấm áp, thân thiện như người cháu nói với cô chú lớn tuổi. "
                                                        "Nói chậm rãi, rõ ràng, ngắt nhẹ trước mỗi con số và nhấn vào số tiền.")
    return r.read()
