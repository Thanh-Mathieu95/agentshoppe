"""AI dựng tin đăng từ MỘT ảnh + lời người bán, và làm bộ ảnh quảng cáo.

Trung thực bằng code, không bằng lời hứa của mô hình:
- Con số (giá, số lượng, dung tích) chỉ lấy từ lời người bán, qua bộ đọc số; không lấy từ ảnh.
- Thông tin mô hình đoán từ ảnh chỉ được điền khi đủ chắc, mọi trường vẫn đọc lại để người bán xác nhận.
- Giá đề xuất do code tính từ giá trên sàn, không bao giờ dưới giá thấp nhất người bán nói.
- Ảnh quảng cáo: AI chỉ vẽ NỀN; sản phẩm là điểm ảnh gốc dán lên, chữ do code viết từ thông tin đã xác nhận.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import uuid

from PIL import Image as PI
from PIL import ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from app import catalog
from app.agent import llm
from app.config import UPLOAD_DIR
from app.models import FieldState, Image, Listing, Seller
from app.services import listings as ls
from app.validators import numbers

log = logging.getLogger(__name__)

IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-2")
MIN_CONF = 0.75
GEN_DIR = UPLOAD_DIR / "gen"
_bg_tasks: dict[int, asyncio.Task] = {}


# ---------------- 1. đọc ảnh + lời nói (một lần gọi) ----------------

def _prompt(transcript: str) -> str:
    cats = {k: {"label": v["label"], "fields": {f["key"]: f["label"] for f in v["fields"]}}
            for k, v in catalog.categories().items()}
    return f"""Bạn nhận diện sản phẩm cho người bán nhỏ trên sàn thương mại điện tử Việt Nam.
Từ ẢNH và LỜI NGƯỜI BÁN, điền thông tin để dựng tin đăng. Trả về DUY NHẤT một JSON.

NGÀNH HÀNG VÀ TRƯỜNG ĐƯỢC PHÉP: {json.dumps(cats, ensure_ascii=False)}

QUY TẮC
- Lời người bán luôn thắng ảnh khi mâu thuẫn.
- Không bịa thương hiệu, chất liệu, nguồn gốc, kích thước. Không chắc thì bỏ trường đó.
- Trường số (price, volume_ml, weight_g, stock) CHỈ điền khi người bán nói; "words" là nguyên văn cụm họ nói.
- Mỗi trường: "from" là "seller" (người bán nói) hoặc "image" (nhìn thấy rõ); confidence 0..1.
- price_words: cụm người bán nói về giá bán. floor_words: cụm nói giá thấp nhất ("không dưới...", "ít nhất...").

JSON:
{{"category": "<một khóa ngành ở trên hoặc null>",
 "description": "một câu dưới 20 từ tả ảnh cho người khiếm thị",
 "fields": {{"<khóa trường>": {{"value": "tiếng Việt", "from": "seller|image", "confidence": 0.9, "words": "..."}}}},
 "price_words": null, "floor_words": null,
 "dominant_color": "#rrggbb màu chủ đạo của sản phẩm",
 "scene": "English: one short background scene that suits this product and its origin, WITHOUT the product"}}

LỜI NGƯỜI BÁN: {transcript or "(không nói gì)"}"""


async def analyze(image_path: str, transcript: str) -> dict | None:
    if not llm.enabled():
        return None
    try:
        data = await llm.vision_json(_prompt(transcript), image_path, effort="none")   # nhanh ~1.5s, đo thấy không kém
    except Exception as e:
        log.warning("shopmaker analyze failed: %s", e)
        return None
    return data if data.get("category") in catalog.categories() else None


def suggest_price(category: str, floor: int | None) -> dict:
    m = catalog.market(category)
    price = max(round(m["median"], -3), floor or 0)
    return {"price": price, "min": m["min"], "max": m["max"], "floor": floor}


def apply(db, seller: Seller, lst: Listing, data: dict) -> dict:
    """Ghi các trường mô hình đọc được vào phiếu (trạng thái HEARD: vẫn phải đọc lại)."""
    filled, price_info = [], None
    tpls = {t_["key"]: t_ for t_ in catalog.category(lst.category)["fields"]}
    got = data.get("fields") or {}
    for key, tpl in tpls.items():
        it = got.get(key) or {}
        if key in ls.NUMERIC_KEYS:
            if key == "price":
                continue
            words = it.get("words") if it.get("from") == "seller" else None
            if words and numbers.parse(words, key):
                ls.set_field(db, seller, lst, key, words, source="voice")
                filled.append(key)
            continue
        val = (it.get("value") or "").strip()
        if not val:
            continue
        by_seller = it.get("from") == "seller"
        if tpl.get("choices") and ls.clean_text_value(lst.category, key, val) not in tpl["choices"]:
            continue   # trường lựa chọn: chỉ nhận đúng một lựa chọn, còn lại để hỏi người bán
        if by_seller or (float(it.get("confidence") or 0) >= MIN_CONF and (tpl["risk"] != "red" or key == "name")):
            ls.set_field(db, seller, lst, key, val, source="voice" if by_seller else "image")
            filled.append(key)
    said = numbers.parse(data.get("price_words") or "", "price")
    floor = numbers.parse(data.get("floor_words") or "", "price")
    if said:
        ls.set_field(db, seller, lst, "price", data["price_words"], source="voice")
        filled.append("price")
    elif floor:
        price_info = suggest_price(lst.category, floor.int_value)
        ls.set_field(db, seller, lst, "price", f"{price_info['price']} đồng", source="system")
        filled.append("price")
    return {"filled": filled, "price": price_info}


# ---------------- 2. ảnh: tách sản phẩm, nền, chữ ----------------

def _font(size: int, bold: bool = True):
    for name in (("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def cutout(path: str) -> PI.Image | None:
    """Tách sản phẩm khỏi nền trơn bằng loang màu từ mép ảnh. Nền rối -> None (dùng kiểu khung ảnh)."""
    # ponytail: loang màu chỉ hợp nền tương đối trơn; cần tách nền ảnh thật phức tạp thì thay bằng mô hình segmentation.
    im = ImageOps.exif_transpose(PI.open(path)).convert("RGB")
    im.thumbnail((900, 900))
    w, h = im.size
    key = (255, 0, 254)
    mark = im.filter(ImageFilter.GaussianBlur(2))
    for p in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        if mark.getpixel(p) != key:
            ImageDraw.floodfill(mark, p, key, thresh=40)
    fg = ImageChops.difference(mark, PI.new("RGB", (w, h), key)).convert("L").point(lambda v: 255 if v else 0)
    fg = fg.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))
    cover = fg.histogram()[255] / (w * h)
    box = fg.getbbox()
    if not box or not 0.05 < cover < 0.7 or (box[2] - box[0]) > 0.97 * w and (box[3] - box[1]) > 0.97 * h:
        return None
    out = im.copy()
    out.putalpha(fg.filter(ImageFilter.GaussianBlur(1.2)))
    return out.crop(box)


def _framed(path: str) -> PI.Image:
    """Không tách được nền: giữ nguyên ảnh thật trong khung bo góc, viền trắng."""
    im = ImageOps.exif_transpose(PI.open(path)).convert("RGB")
    im.thumbnail((760, 760))
    pad = 18
    card = PI.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (255, 255, 255, 255))
    card.paste(im, (pad, pad))
    mask = PI.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, *card.size], radius=28, fill=255)
    card.putalpha(mask)
    return card


def _place(canvas: PI.Image, prod: PI.Image, max_w: float, max_h: float, cx: float, base_y: float) -> None:
    W, H = canvas.size
    k = min(W * max_w / prod.width, H * max_h / prod.height)   # phóng hoặc thu cho vừa khung
    p = prod.resize((max(1, int(prod.width * k)), max(1, int(prod.height * k))), PI.LANCZOS)
    x, y = int(W * cx - p.width / 2), int(H * base_y - p.height)
    sh = PI.new("L", canvas.size, 0)
    ImageDraw.Draw(sh).ellipse([x + p.width * 0.08, y + p.height - 14, x + p.width * 0.92, y + p.height + 22], fill=110)
    canvas.paste((0, 0, 0), mask=sh.filter(ImageFilter.GaussianBlur(18)))
    canvas.paste(p, (x, y), p)


def _luminance(rgb) -> float:
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def theme_color(hex_color: str | None) -> str:
    """Màu shop lấy từ màu sản phẩm, làm đậm tới khi chữ trắng trên nền đạt tương phản ≥ 4.5:1."""
    try:
        rgb = tuple(int((hex_color or "").lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        rgb = (180, 83, 9)
    while 1.05 / (_luminance(rgb) + 0.05) < 4.5:
        rgb = tuple(int(c * 0.9) for c in rgb)
    return "#%02x%02x%02x" % rgb


def _rgb(hex_color: str) -> tuple:
    return tuple(int(hex_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))


def _fallback_bg(size: tuple, color: str) -> PI.Image:
    top, (r, g, b) = (250, 247, 240), _rgb(color)
    low = (int(r * 0.25 + 190), int(g * 0.25 + 185), int(b * 0.25 + 175))
    grad = PI.linear_gradient("L").resize(size)
    return PI.composite(PI.new("RGB", size, low), PI.new("RGB", size, top), grad)


async def _generate_bg(prompt: str, size: str) -> PI.Image | None:
    try:
        r = await llm.client().images.generate(model=IMAGE_MODEL, prompt=prompt, size=size, quality="medium", n=1)
        return PI.open(io.BytesIO(base64.b64decode(r.data[0].b64_json))).convert("RGB")
    except Exception as e:
        log.warning("image generation failed: %s", e)
        return None


def start_backgrounds(listing_id: int, scene: str) -> None:
    """AI vẽ nền (không có sản phẩm) chạy ngầm trong lúc người bán xác nhận thông tin."""
    if not llm.enabled() or not scene:
        return
    rule = ("No product, no bottle, no jar, no package, no text, no letters, no logo, no people. "
            "Photorealistic, soft natural light, gentle depth of field.")
    _bg_tasks[listing_id] = asyncio.gather(
        _generate_bg(f"Product photography backdrop: {scene}. Empty clear surface in the center foreground "
                     f"where a product will be placed. {rule}", "1024x1024"),
        _generate_bg(f"Wide shop banner backdrop: {scene}. Calm, uncluttered, empty space on the left half. {rule}", "1536x1024"),
    )


async def _backgrounds(listing_id: int, wait_s: float) -> tuple:
    """(nền vuông, nền ngang, việc còn đang chạy nếu quá giờ)."""
    task = _bg_tasks.pop(listing_id, None)
    if not task:
        return None, None, None
    try:
        sq, wide = await asyncio.wait_for(asyncio.shield(task), wait_s)
        return sq, wide, None
    except asyncio.TimeoutError:   # chưa xong: dùng nền vẽ bằng code trước, xong thì thay
        return None, None, task
    except Exception:
        return None, None, None


def _save(db, lst: Listing, im: PI.Image, kind: str, extra: dict | None = None) -> Image:
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    path = GEN_DIR / f"{lst.id}_{kind}_{uuid.uuid4().hex[:6]}.jpg"
    im.convert("RGB").save(path, quality=90)
    img = Image(owner_type="listing", owner_id=lst.id, path=str(path), accepted=True,
                quality={"bright": 0.8, "sharp": 2.0}, observations={"kind": kind, "generated": True, **(extra or {})})
    db.add(img)
    db.commit()
    return img


def _product(path: str) -> tuple[PI.Image, bool]:
    c = cutout(path)
    return (c, True) if c is not None else (_framed(path), False)


def make_main(db, lst: Listing, photo: Image, color: str) -> Image:
    """Ảnh bìa: nền trắng, sản phẩm thật ở giữa."""
    prod, cut = _product(photo.path)
    canvas = PI.new("RGB", (1024, 1024), (255, 255, 255))
    _place(canvas, prod, 0.72, 0.72, 0.5, 0.86)
    return _save(db, lst, canvas, "main", {"photo_id": photo.id, "cutout": cut, "color": color})


def _badge(im: PI.Image, text: str) -> None:
    d = ImageDraw.Draw(im)
    f = _font(26, bold=False)
    w = d.textlength(text, font=f)
    d.rounded_rectangle([im.width - w - 52, 22, im.width - 22, 70], radius=24, fill=(255, 255, 255))
    d.text((im.width - w - 37, 31), text, font=f, fill=(60, 60, 60))


def _fit_text(d, text: str, max_w: int, size: int, bold=True):
    f = _font(size, bold)
    while d.textlength(text, font=f) > max_w and size > 22:
        size -= 2
        f = _font(size, bold)
    return f


async def finish_media(db, seller: Seller, lst: Listing, wait_s: float = 25) -> list[str]:
    """Trước khi đọc tóm tắt đăng tin: ghép ảnh bối cảnh, ảnh có chữ, banner shop. Trả về mô tả từng ảnh để đọc."""
    imgs = ls.images(db, lst)
    main = next((i for i in imgs if (i.observations or {}).get("kind") == "main"), None)
    if not main or any((i.observations or {}).get("kind") == "scene" for i in imgs):
        return []
    photo = db.get(Image, main.observations["photo_id"])
    color = theme_color(main.observations.get("color"))
    prod, _ = _product(photo.path)
    bg_sq, bg_wide, pending = await _backgrounds(lst.id, wait_s)
    v = {k: f.value for k, f in ls.fields(db, lst.id).items() if f.value and f.state == FieldState.CONFIRMED}
    name = v.get("name") or ls.name_of(db, lst)
    bits = [v["origin"]] if v.get("origin") else []
    if v.get("volume_ml"):
        bits.append(ls.short_value(lst, "volume_ml", v["volume_ml"]))
    elif v.get("weight_g"):
        bits.append(ls.short_value(lst, "weight_g", v["weight_g"]))
    sub = " · ".join(bits)
    said = []

    scene_img = _save(db, lst, _scene(bg_sq, prod, color), "scene", {"ai_background": bg_sq is not None})
    said.append("một ảnh đặt hàng trong khung cảnh đẹp, có ghi chữ ảnh minh họa")

    card = PI.new("RGB", (1024, 1024), (250, 248, 243))
    _place(card, prod, 0.66, 0.64, 0.5, 0.74)   # sản phẩm nằm trọn phía trên dải chữ
    d = ImageDraw.Draw(card)
    d.rectangle([0, 800, 1024, 1024], fill=_rgb(color))
    d.text((60, 830), name, font=_fit_text(d, name, 904, 64), fill=(255, 255, 255))
    if sub:
        d.text((60, 920), sub, font=_fit_text(d, sub, 904, 40, bold=False), fill=(255, 255, 255))
    text_img = _save(db, lst, card, "text")
    said.append(f"một ảnh có dòng chữ {name}" + (f", {sub.replace(' · ', ', ')}" if sub else ""))

    banner = None
    shop = seller.shop_name or seller.name or name
    line = " · ".join(x for x in (seller.main_products, seller.region) if x)
    if not (seller.theme or {}).get("banner_id"):
        banner = _save(db, lst, _banner(bg_wide, prod, color, shop, line), "banner")
        seller.theme = {"color": color, "banner_id": banner.id}
        db.add(seller)
        said.append("và ảnh bìa cho gian hàng")

    lst.image_ids = [main.id, scene_img.id, text_img.id, photo.id]
    db.add(lst)
    db.commit()
    if pending:   # nền AI chưa xong: đăng ngay bằng nền dự phòng, nền xong thì thay ảnh tại chỗ
        asyncio.create_task(_upgrade_later(pending, prod, color, scene_img.path, banner.path if banner else None, shop, line))
    return said


def _scene(bg: PI.Image | None, prod: PI.Image, color: str) -> PI.Image:
    scene = (bg or _fallback_bg((1024, 1024), color)).resize((1024, 1024))
    _place(scene, prod, 0.6, 0.62, 0.5, 0.82)
    _badge(scene, "Ảnh minh họa bối cảnh")
    return scene


def _banner(bg: PI.Image | None, prod: PI.Image, color: str, shop: str, line: str) -> PI.Image:
    wide = ImageOps.fit(bg or _fallback_bg((1500, 500), color), (1500, 500), PI.LANCZOS)
    shade = PI.linear_gradient("L").rotate(90, expand=True).resize((1500, 500)).point(lambda x: int((255 - x) * 0.92))
    wide.paste(_rgb(color), mask=shade)   # màu shop đậm bên trái để chữ trắng dễ đọc
    _place(wide, prod, 0.3, 0.8, 0.8, 0.92)
    d = ImageDraw.Draw(wide)
    d.text((60, 150), shop, font=_fit_text(d, shop, 820, 84), fill=(255, 255, 255))
    if line:
        d.text((62, 270), line, font=_fit_text(d, line, 820, 40, bold=False), fill=(255, 255, 255))
    return wide


async def _upgrade_later(task, prod, color, scene_path: str, banner_path: str | None, shop: str, line: str) -> None:
    try:
        sq, wide = await task
    except Exception:
        return
    if sq:
        _scene(sq, prod, color).convert("RGB").save(scene_path, quality=90)
    if wide and banner_path:
        _banner(wide, prod, color, shop, line).convert("RGB").save(banner_path, quality=90)


# ---------------- 3. dùng chung: ảnh -> tin nháp; đăng một chạm (Kênh Người Bán) ----------------

async def draft_from_photo(db, seller: Seller, img: Image, words: str) -> dict | None:
    data = await analyze(img.path, words)
    if not data:
        return None
    lst = ls.start_listing(db, seller, data["category"])
    img.owner_type, img.owner_id, img.accepted = "listing", lst.id, True
    img.description = data.get("description")
    db.add(img)
    db.commit()
    out = apply(db, seller, lst, data)
    main = make_main(db, lst, img, data.get("dominant_color") or "#b45309")
    lst.image_ids = [main.id, img.id]
    db.add(lst)
    db.commit()
    start_backgrounds(lst.id, data.get("scene") or "")
    return {"listing": lst, "filled": out["filled"], "price": out["price"]}


def form_view(db, lst: Listing) -> dict:
    fs = ls.fields(db, lst.id)
    m = catalog.market(lst.category)
    return {"listing_id": lst.id, "status": lst.status, "category": catalog.category(lst.category)["label"],
            "container": ls.container(lst), "market": {"min": m["min"], "max": m["max"], "note": m["unit_note"]},
            "images": [f"/api/images/{i}/file" for i in (lst.image_ids or [])],
            "fields": [{"key": t_["key"], "label": t_["label"], "value": fs[t_["key"]].value, "unit": t_.get("unit"),
                        "required": t_["risk"] == "red", "choices": t_.get("choices"), "numeric": t_["key"] in ls.NUMERIC_KEYS,
                        "from": fs[t_["key"]].source.value if fs[t_["key"]].source else None}
                       for t_ in catalog.category(lst.category)["fields"]]}


_RAW_UNIT = {"price": " đồng", "volume_ml": " ml", "weight_g": " gam", "stock": ""}


async def quick_publish(db, seller: Seller, lst: Listing, values: dict[str, str], demo: bool) -> dict:
    """Người bán NHÌN thấy cả tin trên màn hình rồi bấm Đăng: một cú bấm là xác nhận cho mọi ô đang hiện."""
    from datetime import datetime
    fs = ls.fields(db, lst.id)
    problems = []
    for key, val in values.items():
        val = (val or "").strip()
        f = fs.get(key)
        if not f or not val or val == (f.value or ""):
            continue
        raw = val + _RAW_UNIT[key] if key in ls.NUMERIC_KEYS and val.replace(".", "").isdigit() else val
        r = ls.set_field(db, seller, lst, key, raw.replace(".", "") if key in ls.NUMERIC_KEYS else raw, source="voice")
        if not r["ok"]:
            problems.append(ls.label_of(lst, key))
    fs = ls.fields(db, lst.id)
    problems += [ls.label_of(lst, k) for k, f in fs.items() if f.risk.value == "red" and not f.value]
    if problems:
        return {"ok": False, "errors": [f"Kiểm tra lại: {', '.join(dict.fromkeys(problems))}"]}
    for f in fs.values():
        if f.value:
            f.state, f.confirmed_at = FieldState.CONFIRMED, datetime.now()
            db.add(f)
    lst.stock = int(fs["stock"].value)
    db.add(lst)
    db.commit()
    await finish_media(db, seller, lst, wait_s=3)   # bấm Đăng là đăng ngay; nền AI xong sau sẽ tự thay
    ls.save_draft(db, seller, lst, *ls.draft_text_rules(db, lst))   # mô tả ghép từ thông tin đã xác nhận: luôn có nguồn
    errors = [e for e in ls.can_publish(db, seller, lst, log=False)
              if not (e[0] == "NOT_CONFIRMED" and not fs[e[1]].value and fs[e[1]].risk.value != "red")]
    if errors:
        return {"ok": False, "errors": [ls.gate_reason(seller, lst, errors)]}
    ls.publish(db, lst)
    if demo:   # demo: lên sàn ngay
        lst.status, lst.pending_until = "published", None
        db.add(lst)
        db.commit()
    return {"ok": True, "status": lst.status, "product_url": f"#/p/{lst.id}", **form_view(db, lst)}


def remove_image(db, lst: Listing, kind: str) -> bool:
    gone = [i.id for i in ls.images(db, lst) if (i.observations or {}).get("kind") == kind]
    if not gone:
        return False
    lst.image_ids = [i for i in lst.image_ids or [] if i not in gone]
    db.add(lst)
    db.commit()
    return True
