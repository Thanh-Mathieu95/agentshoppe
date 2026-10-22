"""Chấm ảnh, quan sát thuộc tính, kiểm tra đóng gói, đọc biên nhận."""
from __future__ import annotations

import logging
import re

from PIL import Image as PILImage
from PIL import ImageFilter, ImageStat

from app import catalog
from app.agent import llm
from app.models import Image

log = logging.getLogger(__name__)

DARK_BELOW = 0.28
BLURRY_BELOW = 1.25

LISTING_PROMPT = """Bạn là mắt của người bán khiếm thị. Mô tả sản phẩm trong ảnh bằng tiếng Việt đơn giản.
Trả về JSON: {"description": "MỘT câu dưới 20 từ, viết thường, không dấu chấm cuối: vật gì, bao nhiêu, màu, vị trí. Ví dụ: một chai thủy tinh màu vàng sẫm, nắp đỏ, đặt giữa ảnh",
"items":[{"type":"...", "count": n, "volume_ml_est": n|null}], "count": n|null, "volume_ml_est": n|null,
"color": "...", "confidence": 0..1, "photo_issue": null|"dark"|"blurry"|"cut_off"|"cluttered"}
Không đoán khi không chắc: không chắc thì để null."""

PACKING_PROMPT = """Đếm và mô tả các sản phẩm trong ảnh. Trả về JSON:
{"items":[{"type":"...", "count": n, "volume_ml_est": n|null, "notes":"..."}], "count": n|null, "volume_ml_est": n|null,
 "confidence": 0..1, "photo_issue": null|"dark"|"blurry"|"cut_off"|"cluttered"}
Không đoán khi không chắc: nếu không đếm được, đặt count=null và photo_issue phù hợp."""

RECEIPT_PROMPT = """Đây là ảnh biên nhận gửi hàng. Đọc mã vận đơn (mã gửi hàng).
Trả về JSON: {"tracking_code": "chỉ chữ in hoa và số, không dấu cách" | null, "confidence": 0..1,
"photo_issue": null|"dark"|"blurry"|"cut_off"}. Không chắc thì để null."""


def quality_metrics(path: str) -> dict:
    img = PILImage.open(path).convert("L")
    img.thumbnail((320, 320))
    bright = ImageStat.Stat(img).mean[0] / 255
    # Ảnh nét mất nhiều cạnh khi làm mờ nhẹ; ảnh vốn đã mờ thì gần như không đổi.
    e_sharp = ImageStat.Stat(img.filter(ImageFilter.FIND_EDGES)).mean[0]
    e_soft = ImageStat.Stat(img.filter(ImageFilter.GaussianBlur(1.5)).filter(ImageFilter.FIND_EDGES)).mean[0]
    sharp = e_sharp / max(e_soft, 0.01)
    return {"bright": round(bright, 3), "sharp": round(sharp, 3)}


def issue_from(q: dict) -> str | None:
    # ponytail: khung lệch (cut_off) chỉ do mô hình nhìn phát hiện; Pillow chỉ chấm tối/mờ.
    if q["bright"] < DARK_BELOW:
        return "dark"
    if q["sharp"] < BLURRY_BELOW:
        return "blurry"
    return None


def _fixture(image: Image) -> dict | None:
    name = (image.observations or {}).get("_fixture")
    return catalog.demo_photos().get(name) if name else None


async def assess(image: Image, purpose: str) -> dict:
    """Trả {quality, issue, observations, description, source}."""
    q = quality_metrics(image.path)
    issue = issue_from(q)
    obs: dict = {}
    desc = None
    source = "none"
    fx = _fixture(image)
    if llm.enabled():
        prompt = {"listing": LISTING_PROMPT, "packing_check": PACKING_PROMPT, "receipt": RECEIPT_PROMPT}[purpose]
        try:
            data = await llm.vision_json(prompt, image.path)
            obs = {k: v for k, v in data.items() if k not in ("description", "photo_issue")}
            desc = data.get("description")
            issue = issue or data.get("photo_issue")
            source = "llm"
        except Exception as e:  # mạng lỗi -> vẫn còn chấm chất lượng bằng Pillow
            log.warning("vision failed: %s", e)
    if source == "none" and fx:
        obs = dict(fx["observations"])
        desc = fx["description"]
        source = "fixture"
    if purpose == "receipt" and not obs.get("tracking_code") and issue is None:
        obs["tracking_code"] = None
    return {"quality": q, "issue": issue, "observations": obs, "description": desc, "source": source}


def count_items(obs: dict) -> int | None:
    if obs.get("count") is not None:
        return int(obs["count"])
    items = obs.get("items") or []
    counts = [i.get("count") for i in items]
    if not items or any(c is None for c in counts):
        return None
    return int(sum(counts))


def compare_packing(expected: list[dict], obs: dict) -> dict:
    """expected: [{"name","count","volume_ml"}]. Trả {"status": pass|fail|unsure, "need", "seen"}."""
    need = sum(e["count"] for e in expected)
    seen = count_items(obs)
    if seen is None:
        return {"status": "unsure", "need": need, "seen": None}
    if seen != need:
        return {"status": "fail", "need": need, "seen": seen, "reason": "count"}
    vol_exp = next((e.get("volume_ml") for e in expected if e.get("volume_ml")), None)
    vol_obs = obs.get("volume_ml_est")
    if vol_exp and vol_obs and abs(vol_obs - vol_exp) / vol_exp > 0.3:
        return {"status": "fail", "need": need, "seen": seen, "reason": "volume", "vol_exp": vol_exp, "vol_obs": vol_obs}
    return {"status": "pass", "need": need, "seen": seen}


SPOKEN_DIGIT = {"không": "0", "một": "1", "hai": "2", "ba": "3", "bốn": "4", "tư": "4", "năm": "5", "lăm": "5",
                "sáu": "6", "bảy": "7", "bẩy": "7", "tám": "8", "chín": "9"}


def tracking_from_text(text: str) -> str | None:
    """Người bán đọc mã: 'S P X V một hai ba bốn...' hoặc gõ 'SPXV1234 5678'."""
    out = []
    for tok in re.split(r"[\s\-.,]+", (text or "").lower()):
        if tok in SPOKEN_DIGIT:
            out.append(SPOKEN_DIGIT[tok])
        elif re.fullmatch(r"[a-z0-9]+", tok):
            out.append(tok.upper())
    code = "".join(out)
    return code if len(code) >= 8 and any(c.isdigit() for c in code) else None
