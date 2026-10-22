from datetime import date

from sqlmodel import select

from app.db import listing_key_map
from app.mock_shopee import simulator
from app.models import Listing, Order, Seller
from app.services import orders as osv


def setup(db):
    seller = db.get(Seller, 1)
    keys = listing_key_map(db)
    return seller, db.get(Listing, keys["honey_mint"]), db.get(Listing, keys["tea_shan"])


def test_no_accept_when_out_of_stock(db):
    seller, honey, _ = setup(db)
    o = simulator.spawn_order(db, seller, honey, 3, "A", "Huế", 2)   # còn 2 chai
    r = osv.request_action(db, seller, o, "accept")
    assert not r["ok"] and r["data"]["code"] == "OUT_OF_STOCK"
    assert "chỉ còn hai" in r["say"]


def test_no_packed_without_packing_check(db):
    seller, _, _ = setup(db)
    o = db.exec(select(Order).where(Order.external_id == "SPE-1001")).one()
    r = osv.request_action(db, seller, o, "mark_packed")
    assert r["data"]["code"] == "PACKING_NOT_VERIFIED"


def test_no_shipped_without_tracking_or_packing(db):
    seller, _, _ = setup(db)
    o = db.exec(select(Order).where(Order.external_id == "SPE-1001")).one()
    assert osv.request_action(db, seller, o, "mark_shipped")["data"]["code"] == "NOT_PACKED"
    o.status = "packed"
    db.add(o)
    db.commit()
    assert osv.request_action(db, seller, o, "mark_shipped")["data"]["code"] == "NO_TRACKING"
    osv.set_tracking(db, o, "SPXV 1234 5678")
    r = osv.request_action(db, seller, o, "mark_shipped")
    assert r["ok"] and r["confirmation"].two_step and r["confirmation"].action_phrase == "đã gửi rồi"


def test_cancel_needs_reason_and_two_steps(db):
    seller, honey, _ = setup(db)
    o = simulator.spawn_order(db, seller, honey, 1, "B", "Huế", 2)
    assert osv.request_action(db, seller, o, "cancel")["data"]["need_reason"]
    r = osv.request_action(db, seller, o, "cancel", "hết hàng")
    assert r["confirmation"].two_step and "giảm điểm" in r["confirmation"].prompt_text


async def test_accept_by_voice_reduces_stock(db, turn):
    seller, honey, _ = setup(db)
    o = simulator.spawn_order(db, seller, honey, 1, "Lan", "Hà Nội", 2)
    simulator.ingest_order(db, seller, o)
    _, said = await turn("nhận đơn")
    assert "Đã nhận đơn" in said
    db.refresh(o)
    db.refresh(honey)
    assert o.status == "accepted" and honey.stock == 1


async def test_accept_without_details_reads_first(db, turn):
    seller, honey, _ = setup(db)
    o = simulator.spawn_order(db, seller, honey, 1, "Lan", "Hà Nội", 2)   # không ingest -> chưa đọc chi tiết
    _, said = await turn("nhận đơn")
    assert "Nhận thì cô nói 'nhận đơn'" in said
    db.refresh(o)
    assert o.status == "new"
    await turn("nhận đơn")
    db.refresh(o)
    assert o.status == "accepted"


async def test_hello_leads_seller_through_the_order(db, turn):
    seller, honey, _ = setup(db)
    o = simulator.spawn_order(db, seller, honey, 1, "Nguyễn Thị Lan", "Hà Nội", 2)
    _, said = await turn(button="hello")
    assert said.startswith("Chào cô Mai") and "Nguyễn Thị Lan" in said and "nhận đơn" in said
    _, said = await turn("nhận đơn")
    db.refresh(o)
    assert o.status == "accepted"
    _, said = await turn(button="next_task")      # việc tiếp theo: đóng gói đơn gấp nhất (mẫu: Trần Văn Nam, hạn mai)
    assert "cần" in said and "nói 'chụp'" in said


def test_plan_shipping_trip(db):
    seller, honey, _ = setup(db)
    seller.shipping_days = ["thu"]
    today = date(2026, 10, 19)   # thứ Hai
    o1 = simulator.spawn_order(db, seller, honey, 1, "X", "Huế", 2)
    o1.ship_by = o1.ship_by.replace(year=2026, month=10, day=23)   # thứ Sáu -> kịp thứ Năm
    o2 = simulator.spawn_order(db, seller, honey, 1, "Y", "Huế", 2)
    o2.ship_by = o2.ship_by.replace(year=2026, month=10, day=21)   # thứ Tư -> không kịp
    for o in (o1, o2):
        o.status = "accepted"
        db.add(o)
    db.commit()
    r = osv.plan_shipping_trip(db, seller, today=today)
    assert o2.id in r["data"]["late"]
    assert o1.id in r["data"]["plan"]["2026-10-22"]
