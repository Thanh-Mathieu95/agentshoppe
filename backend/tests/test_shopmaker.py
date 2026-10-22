"""AI dựng tin đăng từ ảnh: số chỉ lấy từ lời người bán, giá đề xuất không dưới giá sàn, ảnh giữ nguyên sản phẩm."""
from PIL import Image as PI

from app.agent import flow, rt_tools
from app.agent import session as sessions
from app.demo_photos import PHOTO_DIR
from app.models import FieldState, Image, Listing, Seller
from app.services import listings as ls
from app.services import shopmaker

AI = {"category": "honey", "description": "một chai mật ong vàng sẫm, nắp đỏ",
      "fields": {"name": {"value": "Mật ong bạc hà", "from": "seller", "confidence": 0.95},
                 "origin": {"value": "Hà Giang", "from": "seller", "confidence": 0.9},
                 "stock": {"value": "15", "from": "seller", "words": "có mười lăm chai"},
                 "volume_ml": {"value": "500", "from": "image", "confidence": 0.9},          # số từ ảnh: không lấy
                 "container": {"value": "chai thủy tinh", "from": "image", "confidence": 0.9},
                 "harvest_time": {"value": "tháng ba", "from": "image", "confidence": 0.4}},  # đoán: không điền
      "price_words": None, "floor_words": "không dưới hai trăm nghìn",
      "dominant_color": "#f2c14e", "scene": "wooden table, mint flowers"}


def test_cutout_keeps_product_pixels():
    out = shopmaker.cutout(str(PHOTO_DIR / "honey_1x500.jpg"))
    assert out is not None and out.mode == "RGBA"
    assert out.width < 400                                   # chỉ còn cái chai, không cả nền


def test_theme_color_readable():
    c = shopmaker.theme_color("#f2c14e")                       # vàng nhạt -> làm đậm để chữ trắng đọc được
    rgb = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    assert 1.05 / (shopmaker._luminance(rgb) + 0.05) >= 4.5


async def test_quick_listing_from_photo(db, monkeypatch):
    async def fake_analyze(path, words):
        assert "mười lăm" in words                            # lời thật người bán vừa nói được đưa vào
        return AI
    monkeypatch.setattr(shopmaker, "analyze", fake_analyze)
    monkeypatch.setattr(shopmaker, "start_backgrounds", lambda *a: None)
    seller = db.get(Seller, 1)
    s = sessions.get(seller.id)
    r = await rt_tools.run(db, seller, s, "sell_from_photo", {})
    assert r["ok"] and s.quick_since
    rt_tools.record_heard(s, "mật ong bạc hà Hà Giang, có mười lăm chai, bán không dưới hai trăm nghìn")
    img = Image(owner_type="listing", owner_id=0, path=str(PHOTO_DIR / "honey_1x500.jpg"))
    db.add(img)
    db.commit()
    ev = await flow.on_image(flow.Ctx(db=db, seller=seller, s=s), img.id, "listing")
    lst = db.get(Listing, s.active_listing_id)
    fs = ls.fields(db, lst.id)
    assert fs["name"].value == "Mật ong bạc hà" and fs["stock"].value == "15"
    assert fs["volume_ml"].value is None and fs["harvest_time"].value is None
    assert int(fs["price"].value) >= 200000                   # đề xuất không dưới giá sàn
    assert all(f.state != FieldState.CONFIRMED for f in fs.values() if f.value)   # vẫn phải đọc lại
    assert s.pending is not None and any(e["type"] == "listing_live" for e in ev)
    assert "đề xuất" in ev[0]["text"]
    kinds = [(i.observations or {}).get("kind") for i in ls.images(db, lst)]
    assert "main" in kinds


async def test_finish_media_uses_confirmed_text(db):
    seller = db.get(Seller, 1)
    lst = ls.start_listing(db, seller, "honey")
    photo = Image(owner_type="listing", owner_id=lst.id, path=str(PHOTO_DIR / "honey_1x500.jpg"), accepted=True)
    db.add(photo)
    db.commit()
    main = shopmaker.make_main(db, lst, photo, "#f2c14e")
    f = ls.fields(db, lst.id)["name"]
    f.value, f.state = "Mật ong bạc hà", FieldState.CONFIRMED
    db.add(f)
    db.commit()
    said = await shopmaker.finish_media(db, seller, lst)
    assert said and lst.image_ids[0] == main.id and lst.image_ids[-1] == photo.id
    kinds = {(db.get(Image, i).observations or {}).get("kind") for i in lst.image_ids}
    assert {"main", "scene", "text"} <= kinds
    assert await shopmaker.finish_media(db, seller, lst) == []   # không làm lại lần hai


def test_demo_mode_publishes_after_ten_seconds(db):
    from app import config
    lst = ls.start_listing(db, db.get(Seller, 1), "honey")
    config.DEMO["on"] = True
    try:
        ls.publish(db, lst)
        assert flow.wait_words(lst) in ("mười giây", "chín giây")
    finally:
        config.DEMO["on"] = False
    ls.publish(db, lst)
    assert flow.wait_words(lst) == "mười phút"

async def test_quick_publish_one_click(db, monkeypatch):
    async def fake_analyze(path, words):
        return AI
    monkeypatch.setattr(shopmaker, "analyze", fake_analyze)
    monkeypatch.setattr(shopmaker, "start_backgrounds", lambda *a: None)
    seller = db.get(Seller, 1)
    img = Image(owner_type="listing", owner_id=0, path=str(PHOTO_DIR / "honey_1x500.jpg"))
    db.add(img)
    db.commit()
    out = await shopmaker.draft_from_photo(db, seller, img, "")
    lst = out["listing"]
    view = shopmaker.form_view(db, lst)
    assert {f["key"] for f in view["fields"] if f["value"]} >= {"name", "price", "stock"}
    r = await shopmaker.quick_publish(db, seller, lst, {"volume_ml": ""}, demo=True)
    assert not r["ok"] and "dung tích" in r["errors"][0]           # ô bắt buộc trống -> không đăng
    r = await shopmaker.quick_publish(db, seller, lst, {"volume_ml": "500", "price": "250.000"}, demo=True)
    assert r["ok"] and r["status"] == "published"
    assert ls.fields(db, lst.id)["price"].value == "250000"
    assert len(lst.image_ids) == 4 and lst.public_description