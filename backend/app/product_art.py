"""Vẽ ảnh sản phẩm mẫu cho sàn giả lập (Pillow, vẽ 2x rồi thu nhỏ cho mịn)."""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 1200  # vẽ ở 1200 rồi thu về 600
PALETTE = {
    "honey": [(255, 241, 214), (255, 214, 153)],
    "tea": [(226, 245, 226), (176, 222, 180)],
    "handicraft": [(255, 228, 236), (246, 186, 205)],
    "candle": [(240, 232, 255), (207, 190, 245)],
    "dried_food": [(250, 232, 220), (228, 186, 160)],
}


def _font(size: int):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _bg(cat: str, seed: int) -> Image.Image:
    a, b = PALETTE.get(cat, PALETTE["honey"])
    g = Image.new("RGB", (1, 2))
    g.putpixel((0, 0), a)
    g.putpixel((0, 1), b)
    img = g.resize((S, S), Image.BILINEAR)
    d = ImageDraw.Draw(img, "RGBA")
    rnd = random.Random(seed)
    for _ in range(14):
        r = rnd.randint(40, 160)
        x, y = rnd.randint(0, S), rnd.randint(0, S)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 40))
    # bàn gỗ
    d.rectangle([0, int(S * .78), S, S], fill=(140, 96, 62, 255))
    for i in range(6):
        y = int(S * .78) + i * 45
        d.line([0, y, S, y + rnd.randint(-8, 8)], fill=(110, 72, 44, 120), width=4)
    return img


def _shadow(img: Image.Image, box):
    sh = Image.new("L", img.size, 0)
    ImageDraw.Draw(sh).ellipse(box, fill=110)
    sh = sh.filter(ImageFilter.GaussianBlur(28))
    img.paste((60, 35, 20), (0, 0), sh)


def _label(d, x0, y0, x1, y1, text, color=(255, 250, 235), ink=(90, 50, 10)):
    d.rounded_rectangle([x0, y0, x1, y1], radius=18, fill=color, outline=ink, width=4)
    size = int((y1 - y0) * .34)
    f = _font(size)
    while d.textlength(text, font=f) > (x1 - x0) * .86 and size > 12:
        size -= 3
        f = _font(size)
    tw = d.textlength(text, font=f)
    d.text(((x0 + x1 - tw) / 2, (y0 + y1) / 2 - (y1 - y0) * .2), text, fill=ink, font=f)


def _honey(img, d, variant, label):
    n = 2 if variant == "pair" else 1
    for i in range(n):
        cx = S // 2 + (i - (n - 1) / 2) * 330
        w, h = (300, 470) if variant != "big" else (380, 560)
        base = int(S * .82)
        _shadow(img, [cx - w / 2 - 20, base - 40, cx + w / 2 + 20, base + 40])
        d.rounded_rectangle([cx - w / 2, base - h, cx + w / 2, base], radius=60, fill=(214, 128, 18), outline=(120, 64, 8), width=8)
        d.rounded_rectangle([cx - w / 2 + 26, base - h + 40, cx - w / 2 + 70, base - 60], radius=20, fill=(255, 220, 140, 150))
        d.rectangle([cx - w * .28, base - h - 70, cx + w * .28, base - h], fill=(230, 230, 236), outline=(150, 150, 160), width=5)
        d.rounded_rectangle([cx - w * .33, base - h - 120, cx + w * .33, base - h - 60], radius=14, fill=(196, 30, 36))
        _label(d, cx - w / 2 + 30, base - h * .62, cx + w / 2 - 30, base - h * .3, label)
    # tổ ong
    for k in range(5):
        x, y = 160 + k * 90, 170 + (k % 2) * 52
        pts = [(x + 52 * math.cos(math.pi / 3 * j), y + 52 * math.sin(math.pi / 3 * j)) for j in range(6)]
        d.polygon(pts, outline=(214, 150, 40, 200), width=6)


def _tea(img, d, variant, label):
    base = int(S * .82)
    _shadow(img, [300, base - 40, 900, base + 40])
    d.rounded_rectangle([370, base - 560, 830, base], radius=40, fill=(46, 125, 50), outline=(20, 70, 25), width=8)
    d.polygon([(370, base - 560), (830, base - 560), (790, base - 640), (410, base - 640)], fill=(56, 142, 60))
    _label(d, 410, base - 380, 790, base - 230, label, color=(240, 255, 236), ink=(20, 80, 25))
    for k in range(7):
        x, y = 160 + k * 140, 180 + (k % 3) * 50
        d.ellipse([x, y, x + 120, y + 55], fill=(67, 160, 71, 210))
        d.line([x + 10, y + 28, x + 110, y + 28], fill=(30, 90, 35, 200), width=4)


def _handicraft(img, d, variant, label):
    base = int(S * .82)
    _shadow(img, [220, base - 50, 980, base + 40])
    cols = [(198, 40, 40), (25, 25, 25), (255, 193, 7), (21, 101, 192), (46, 125, 50)]
    x0, x1 = 240, 960
    top = base - 520
    stripe = 520 // 10
    for i in range(10):
        y = top + i * stripe
        d.rectangle([x0, y, x1, y + stripe], fill=cols[i % len(cols)])
        if i % 2 == 0:
            for x in range(x0, x1, 60):
                d.polygon([(x, y + stripe / 2), (x + 30, y + 6), (x + 60, y + stripe / 2), (x + 30, y + stripe - 6)], fill=(255, 255, 255, 220))
    for x in range(x0 + 10, x1, 40):
        d.line([x, base, x, base + 50], fill=(198, 40, 40), width=8)
    _label(d, 380, 120, 820, 240, label, color=(255, 255, 255), ink=(150, 20, 20))


def _candle(img, d, variant, label):
    base = int(S * .82)
    _shadow(img, [340, base - 40, 860, base + 40])
    d.rounded_rectangle([380, base - 420, 820, base], radius=50, fill=(255, 255, 255, 230), outline=(140, 120, 180), width=8)
    d.rectangle([400, base - 330, 800, base - 20], fill=(244, 236, 214))
    d.line([600, base - 330, 600, base - 400], fill=(60, 60, 60), width=8)
    flame = Image.new("RGBA", img.size, (0, 0, 0, 0))
    fd = ImageDraw.Draw(flame)
    fd.ellipse([555, base - 560, 645, base - 395], fill=(255, 167, 38, 255))
    fd.ellipse([575, base - 520, 625, base - 410], fill=(255, 241, 118, 255))
    glow = flame.filter(ImageFilter.GaussianBlur(30))
    img.paste(glow, (0, 0), glow)
    img.paste(flame, (0, 0), flame)
    _label(d, 430, base - 250, 770, base - 120, label, color=(255, 255, 255), ink=(90, 60, 140))


def _dried(img, d, variant, label):
    base = int(S * .82)
    _shadow(img, [220, base - 40, 980, base + 40])
    d.rounded_rectangle([230, base - 120, 970, base], radius=30, fill=(161, 110, 70), outline=(100, 60, 30), width=6)
    rnd = random.Random(len(label))
    for i in range(6):
        x = 280 + i * 110
        h = rnd.randint(340, 430)
        d.rounded_rectangle([x, base - 120 - h, x + 80, base - 110], radius=24, fill=(120, 40, 25), outline=(70, 20, 10), width=6)
        d.line([x + 20, base - 110 - h + 40, x + 60, base - 140], fill=(160, 70, 40), width=6)
    d.line([250, 200, 950, 200], fill=(90, 60, 30), width=10)
    _label(d, 380, 240, 820, 360, label, color=(255, 245, 230), ink=(110, 40, 20))


DRAW = {"honey": _honey, "tea": _tea, "handicraft": _handicraft, "candle": _candle, "dried_food": _dried}


def render(cat: str, label: str, path: Path, variant: str = "", seed: int = 0) -> Path:
    img = _bg(cat, seed)
    d = ImageDraw.Draw(img, "RGBA")
    DRAW.get(cat, _honey)(img, d, variant, label)
    img = img.resize((S // 2, S // 2), Image.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=88)
    return path
