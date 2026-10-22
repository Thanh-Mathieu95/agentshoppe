"""Định tuyến: từ khóa điều khiển xử lý bằng code trước; còn lại cho LLM (nếu bật) hoặc bộ luật."""
from app import config
from app.agent import flow, llm

HARD = ("nói lại", "nhắc lại", "chậm thôi", "nói chậm", "dừng", "rút lại", "thôi không đăng", "đúng", "sai")


def is_hard(text: str) -> bool:
    return any(text == k or text.startswith(k + " ") for k in HARD)


def use_llm(ctx) -> bool:
    return (config.AGENT_MODE == "llm" and llm.enabled() and not is_hard(flow.norm(ctx.text))
            and not ctx.s.awaiting)
