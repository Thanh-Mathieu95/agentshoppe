import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
UPLOAD_DIR = BACKEND_DIR / "uploads"


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env(BACKEND_DIR / ".env")


def _f(name: str, default: float) -> float:
    return float(os.environ.get(name) or default)


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or None
LLM_MODEL = os.environ.get("LLM_MODEL", "")
VISION_MODEL = os.environ.get("VISION_MODEL") or LLM_MODEL
# rules: agent luật cố định, chạy không cần mạng; llm: gọi mô hình có tool calling
AGENT_MODE = os.environ.get("AGENT_MODE") or ("llm" if OPENAI_API_KEY and LLM_MODEL else "rules")
STT_PROVIDER = os.environ.get("STT_PROVIDER", "browser")   # browser | openai
TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "browser")   # browser | openai
STT_MODEL = os.environ.get("STT_MODEL", "gpt-4o-mini-transcribe")
TTS_MODEL = os.environ.get("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.environ.get("TTS_VOICE", "alloy")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'bkrc.db'}")

CONFIRM_TIMEOUT_S = _f("CONFIRM_TIMEOUT_S", 30)
PENDING_PUBLISH_MIN = _f("PENDING_PUBLISH_MIN", 10)
DEMO_PENDING_S = 10
DEMO = {"on": os.environ.get("DEMO_MODE", "0") == "1"}   # bật/tắt lúc chạy ở bảng demo


def pending_seconds() -> int:
    """Thời gian chờ trước khi tin lên sàn (để kịp 'rút lại'). Chế độ demo: 10 giây."""
    return DEMO_PENDING_S if DEMO["on"] else int(PENDING_PUBLISH_MIN * 60)
RUBBER_STAMP_MS = _f("RUBBER_STAMP_MS", 2000)
ASR_CONF_THRESHOLD = _f("ASR_CONF_THRESHOLD", 0.85)
MAX_PHOTO_ATTEMPTS = 3
MAX_TOOL_STEPS = 6
