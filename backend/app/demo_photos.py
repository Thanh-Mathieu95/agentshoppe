"""Sinh ảnh mẫu cho demo khi không có camera/mô hình nhìn (vẽ bằng Pillow)."""
import json

from PIL import Image as PILImage
from PIL import ImageDraw, ImageEnhance, ImageFilter, ImageFont

from app.config import DATA_DIR

PHOTO_DIR = DATA_DIR / "demo_photos"

META = {
    "honey_1x500_dark.jpg": {
        "label": "1 chai nửa lít (tối)",
        "observations": {"items": [{"type": "honey", "count": 1, "volume_ml_est": 500}], "count": 1, "volume_ml_est": 500, "confidence": 0.5},
        "description": "một chai mật ong, nhưng ảnh rất tối",
    },
    "honey_1x500_blurry.jpg": {
        "label": "1 chai nửa lít (mờ)",
        "observations": {"items": [{"type": "honey", "count": 1, "volume_ml_est": 500}], "count": 1, "volume_ml_est": 500, "confidence": 0.5},
        "description": "một chai mật ong, nhưng ảnh bị mờ",
    },
    "honey_1x500.jpg": {
        "label": "1 chai nửa lít",
        "observations": {"items": [{"type": "honey", "count": 1, "volume_ml_est": 500}], "count": 1, "volume_ml_est": 500, "color": "vàng sẫm", "confidence": 0.85},
        "description": "một chai thủy tinh nhỏ, cỡ nửa lít, mật màu vàng sẫm, đặt giữa ảnh, nắp đỏ",
    },
    "honey_2x500.jpg": {
        "label": "2 chai nửa lít",
        "observations": {"items": [{"type": "honey", "count": 2, "volume_ml_est": 500}], "count": 2, "volume_ml_est": 500, "color": "vàng sẫm", "confidence": 0.85},
        "description": "hai chai thủy tinh nhỏ, mỗi chai cỡ nửa lít, mật màu vàng sẫm",
    },
    "honey_1x1000.jpg": {
        "label": "1 chai một lít",
        "observations": {"items": [{"type": "honey", "count": 1, "volume_ml_est": 1000}], "count": 1, "volume_ml_est": 1000, "color": "vàng sẫm", "confidence": 0.8},
        "description": "một chai thủy tinh to, cỡ một lít, mật màu vàng sẫm",
    },
    "receipt_spx.jpg": {
        "label": "Biên nhận bưu cục",
        "observations": {"tracking_code": "SPXV12345678", "confidence": 0.9},
        "description": "tờ biên nhận gửi hàng",
    },
}


def _bottle(d: ImageDraw.ImageDraw, x: int, base_y: int, scale: float) -> None:
    w, h = int(90 * scale), int(170 * scale)
    top = base_y - h
    d.rounded_rectangle([x, top, x + w, base_y], radius=int(14 * scale), fill=(186, 112, 20), outline=(90, 50, 10), width=3)
    d.rectangle([x + w * 0.3, top - 30 * scale, x + w * 0.7, top], fill=(200, 200, 210))
    d.rectangle([x + w * 0.25, top - 48 * scale, x + w * 0.75, top - 30 * scale], fill=(200, 30, 30))
    d.rectangle([x + 8, top + h * 0.35, x + w - 8, top + h * 0.65], fill=(250, 240, 210))


def _scene(n: int, scale: float) -> PILImage.Image:
    img = PILImage.new("RGB", (640, 480), (225, 215, 195))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 360, 640, 480], fill=(150, 105, 70))
    total = n * 90 * scale + (n - 1) * 40
    x = int(320 - total / 2)
    for _ in range(n):
        _bottle(d, x, 400, scale)
        x += int(90 * scale + 40)
    return img


def _receipt() -> PILImage.Image:
    img = PILImage.new("RGB", (640, 480), (90, 90, 95))
    d = ImageDraw.Draw(img)
    d.rectangle([120, 40, 520, 440], fill=(250, 250, 245))
    try:
        font = ImageFont.truetype("arial.ttf", 34)
        small = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = small = ImageFont.load_default()
    d.text((150, 70), "BIEN NHAN GUI HANG", fill=(0, 0, 0), font=small)
    d.text((150, 130), "Ma van don:", fill=(0, 0, 0), font=small)
    d.text((150, 170), "SPXV 1234 5678", fill=(0, 0, 0), font=font)
    d.text((150, 260), "Nguoi nhan: Nguyen Thi Lan", fill=(40, 40, 40), font=small)
    d.text((150, 300), "Ha Noi", fill=(40, 40, 40), font=small)
    return img


def generate() -> None:
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    one = _scene(1, 1.0)
    one.save(PHOTO_DIR / "honey_1x500.jpg", quality=90)
    ImageEnhance.Brightness(one).enhance(0.18).save(PHOTO_DIR / "honey_1x500_dark.jpg", quality=90)
    one.filter(ImageFilter.GaussianBlur(7)).save(PHOTO_DIR / "honey_1x500_blurry.jpg", quality=90)
    _scene(2, 1.0).save(PHOTO_DIR / "honey_2x500.jpg", quality=90)
    _scene(1, 1.6).save(PHOTO_DIR / "honey_1x1000.jpg", quality=90)
    _receipt().save(PHOTO_DIR / "receipt_spx.jpg", quality=90)
    (DATA_DIR / "demo_photos.json").write_text(json.dumps(META, ensure_ascii=False, indent=2), encoding="utf-8")
