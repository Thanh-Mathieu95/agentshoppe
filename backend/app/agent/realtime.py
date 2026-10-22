"""Phiên thoại thời gian thực (OpenAI Realtime qua WebRTC).

Realtime chỉ là tai và miệng: nghe liên tục (VAD), cho ngắt lời, đọc câu backend đưa.
Bộ não vẫn là orchestrator + Confirmation Engine: mỗi câu người bán nói (bản ghi thật) đi qua handle_turn.
Vì create_response=false, mô hình giọng nói không tự trả lời và không thể tự xác nhận thay người bán.
"""
import os

import httpx

from app import config
from app.speech.stt import PROMPT

RT_MODEL = os.environ.get("RT_MODEL", "gpt-realtime-2.1")
RT_VOICE = os.environ.get("RT_VOICE", "marin")

VOICE_INSTRUCTIONS = (
    "Bạn là giọng nói của trợ lý 'Bạn Bán Hàng' cho người bán vùng cao, nhiều người lớn tuổi hoặc khiếm thị. "
    "Phát âm chuẩn tiếng Việt giọng Hà Nội, rõ từng tiếng, đủ sáu thanh điệu, không pha giọng nước ngoài. "
    "Nói chậm, to rõ, ấm áp như người cháu nói với cô chú. Ngắt nghỉ rõ ở mỗi dấu phẩy và dấu chấm. "
    "Đọc con số thật chậm và nhấn vào số. "
    "Bạn KHÔNG tự trả lời người bán. Bạn chỉ đọc NGUYÊN VĂN câu được giao trong từng lượt, "
    "không thêm, không bớt, không đổi con số, không tự hỏi thêm."
)


async def create_session(speed: float = 0.9, instructions: str | None = None, tools: list | None = None) -> dict:
    """Không có tools: chỉ là tai/miệng (đọc nguyên văn). Có tools: mô hình là người trò chuyện, làm việc qua công cụ."""
    agent = bool(tools)
    session = {
        "type": "realtime", "model": RT_MODEL, "instructions": instructions or VOICE_INSTRUCTIONS,
        "audio": {
            "input": {
                "transcription": {"model": config.STT_MODEL or "gpt-transcribe", "language": "vi", "prompt": PROMPT},
                "noise_reduction": {"type": "near_field"},
                # người lớn tuổi hay ngập ngừng: chờ hết câu mới coi là xong lượt
                "turn_detection": {"type": "semantic_vad", "eagerness": "low", "create_response": agent, "interrupt_response": True},
            },
            # kéo chậm âm thanh làm giọng méo; để mô hình tự nói chậm, chỉ giảm khi người bán xin "nói chậm hơn"
            "output": {"voice": RT_VOICE, "speed": 1.0 if speed >= 0.9 else max(0.75, speed)},
        },
    }
    if agent:
        session["tools"] = tools
        session["tool_choice"] = "auto"
    body = {"session": session}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post("https://api.openai.com/v1/realtime/client_secrets", json=body,
                         headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"})
    r.raise_for_status()
    j = r.json()
    return {"client_secret": j["value"], "model": RT_MODEL, "expires_at": j.get("expires_at")}
