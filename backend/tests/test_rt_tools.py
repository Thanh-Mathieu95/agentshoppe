"""Bộ não realtime: công cụ hồ sơ, xác nhận bằng lời THẬT của người bán, đăng hàng."""
from app.agent import rt_tools
from app.agent import session as sessions
from app.models import FieldState, Seller
from app.services import listings as ls


def draft(db) -> Seller:
    s = Seller(name="", honorific="", onboarded=False, uses_assistant=True, shipping_days=[])
    db.add(s)
    db.commit()
    return s


async def run(db, seller, tool, **args):
    return await rt_tools.run(db, seller, sessions.get(seller.id), tool, args)


async def answer(db, seller, text):
    """Người bán nói (bản ghi nhận dạng) rồi mô hình gọi confirm."""
    rt_tools.record_heard(sessions.get(seller.id), text)
    return await run(db, seller, "confirm")


async def test_profile_by_conversation(db):
    s = draft(db)
    r = await run(db, s, "update_profile", name="Lò Thị Mai", honorific="cô", region="Hà Giang")
    assert "tên cửa hàng" in r["missing"] and "mặt hàng chính" in r["missing"]
    r = await run(db, s, "update_profile", phone="09 12 34 56 78", shop_name="Mật ong Cô Mai",
                  main_products="mật ong, chè", shipping_days=["tue", "fri"])
    assert r["missing"] == [] and r["saved"]["phone"] == "0912345678"
    r = await run(db, s, "update_profile", phone="123")
    assert r["problems"]                                  # số điện thoại sai không được lưu
    r = await run(db, s, "complete_profile")
    assert r["need_confirmation"] and "Mật ong Cô Mai" in r["say"] and "thứ Ba và thứ Sáu" in r["say"]
    assert r["say"].startswith("Cháu đọc lại hồ sơ của cô")
    assert "không chín một hai" in r["say"]               # đọc số điện thoại từng chữ số
    r = await answer(db, s, "đúng rồi cháu")
    db.refresh(s)
    assert s.onboarded and "đã lưu" in r["say"]


async def test_confirm_uses_real_transcript_not_model(db):
    s = draft(db)
    await run(db, s, "update_profile", name="An", honorific="anh", region="Sơn La", shop_name="Shop An",
              main_products="chè", shipping_days=["mon"])
    await run(db, s, "complete_profile")
    r = await answer(db, s, "sai rồi")                    # người bán nói sai -> không lưu dù mô hình muốn gì
    db.refresh(s)
    assert not s.onboarded and "need_confirmation" not in r


async def test_confirm_without_seller_speech_does_nothing(db):
    s = draft(db)
    await run(db, s, "update_profile", name="An", honorific="anh", region="Sơn La", shop_name="Shop An",
              main_products="chè", shipping_days=["mon"])
    await run(db, s, "complete_profile")
    rt_tools.wait_heard.__defaults__ = (0.2,)            # chờ ngắn trong test
    try:
        r = await run(db, s, "confirm")                   # mô hình gọi confirm khi người bán chưa nói gì
    finally:
        rt_tools.wait_heard.__defaults__ = (4.0,)
    db.refresh(s)
    assert not r["ok"] and not s.onboarded


async def test_listing_by_conversation(db):
    seller = db.get(Seller, 1)
    r = await run(db, seller, "start_listing", category="honey")
    assert "tên là gì" in r["say"]
    lid = r["listing_id"]
    r = await run(db, seller, "set_field", listing_id=lid, key="name", raw_text="mật ong rừng nhà nuôi", source="voice")
    assert r["need_confirmation"] and "Mật ong rừng nhà nuôi" in r["say"]
    r = await answer(db, seller, "đúng")
    assert "chụp" in r["say"].lower()                     # tên xong -> xin ảnh
    lst = ls.fields(db, lid)
    assert lst["name"].state == FieldState.CONFIRMED
    r = await run(db, seller, "set_field", listing_id=lid, key="price", raw_text="bảy trăm nghìn", source="voice")
    assert "BẢY" in r["say"] and r["need_confirmation"]
    r = await answer(db, seller, "không, ba trăm nghìn")
    assert "ba trăm nghìn đồng" in r["say"]
    assert ls.fields(db, lid)["price"].value == "300000"


async def test_accept_order_after_hearing_details(db):
    from app.db import listing_key_map
    from app.mock_shopee import simulator
    from app.models import Listing
    seller = db.get(Seller, 1)
    honey = db.get(Listing, listing_key_map(db)["honey_mint"])
    o = simulator.spawn_order(db, seller, honey, 1, "Lan", "Hà Nội", 2)
    simulator.ingest_order(db, seller, o)                     # trợ lý đã đọc đủ chi tiết đơn
    rt_tools.record_heard(sessions.get(1), "Nhận đơn đi cháu")
    r = await run(db, seller, "request_order_action", order_id=o.id, action="accept")
    db.refresh(o)
    assert o.status == "accepted" and "Đã nhận đơn" in r["say"]


async def test_accept_order_without_hearing_details_asks_first(db):
    from app.db import listing_key_map
    from app.mock_shopee import simulator
    from app.models import Listing
    seller = db.get(Seller, 1)
    honey = db.get(Listing, listing_key_map(db)["honey_mint"])
    o = simulator.spawn_order(db, seller, honey, 1, "Lan", "Hà Nội", 2)   # chưa đọc chi tiết cho người bán
    rt_tools.record_heard(sessions.get(1), "nhận đơn")
    r = await run(db, seller, "request_order_action", order_id=o.id, action="accept")
    db.refresh(o)
    assert o.status == "new" and r["need_confirmation"]


def test_tools_schema_is_flat():
    tools = rt_tools.rt_tools()
    names = {t["name"] for t in tools}
    assert {"update_profile", "complete_profile", "confirm", "set_field", "request_order_action"} <= names
    assert all(t["type"] == "function" and "parameters" in t for t in tools)


def test_instructions_onboarding(db):
    s = draft(db)
    text = rt_tools.instructions(db, s, sessions.get(s.id))
    assert "HỒ SƠ CHƯA XONG" in text and "tên người bán" in text
