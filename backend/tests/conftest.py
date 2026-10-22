import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="bkrc_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["AGENT_MODE"] = "rules"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TTS_PROVIDER"] = "browser"

import pytest  # noqa: E402

from app.agent import session as sessions  # noqa: E402
from app.db import get_session, reset  # noqa: E402

@pytest.fixture
def db():
    reset()   # tạo lại DB + ảnh mẫu
    sessions.reset_all()
    with get_session() as s:
        yield s


@pytest.fixture
def turn():
    """Gửi một lượt như điện thoại gửi; mặc định trả lời sau 3 giây (không kích hoạt chống gật đầu)."""
    from app.agent.orchestrator import handle_turn

    async def _turn(text=None, button=None, image=None, purpose="listing", latency_ms=3000, confidence=None, typ=None):
        if image:
            inp = {"type": "image", "image_id": image, "purpose": purpose}
        elif button:
            inp = {"type": "button", "value": button}
        elif typ:
            inp = {"type": typ}
        else:
            inp = {"type": "text", "text": text, "confidence": confidence}
        inp["latency_ms"] = latency_ms
        ev = await handle_turn(1, inp)
        return ev, " ".join(e["text"] for e in ev if e["type"] == "speak")

    return _turn


def demo_image(db, name: str) -> int:
    import shutil
    import uuid

    from app.config import UPLOAD_DIR
    from app.demo_photos import PHOTO_DIR
    from app.models import Image
    UPLOAD_DIR.mkdir(exist_ok=True)
    dest = UPLOAD_DIR / f"test_{uuid.uuid4().hex[:6]}_{name}"
    shutil.copy(PHOTO_DIR / name, dest)
    img = Image(owner_type="listing", owner_id=0, path=str(dest), observations={"_fixture": name})
    db.add(img)
    db.commit()
    return img.id
