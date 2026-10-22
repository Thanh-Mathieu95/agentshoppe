"""Kịch bản lỗi (mục 17.2): mỗi kịch bản phải sinh BlockedError đúng lớp. Chạy qua đúng đường ống thật (handle_turn)."""
from sqlmodel import select

from app.agent import session as sessions
from app.confirm.engine import log_confirmation
from app.db import listing_key_map
from app.mock_shopee import simulator
from app.models import BlockedError, BuyerMessage, FieldState, Listing, Order, Seller
from app.services import listings as ls
from tests.conftest import demo_image


def blocked(db, code=None, layer=None):
    q = select(BlockedError)
    rows = db.exec(q).all()
    return [b for b in rows if (code is None or b.code == code) and (layer is None or b.layer == layer)]


def listing(db) -> Listing:
    return db.get(Listing, sessions.get(1).active_listing_id)


def field(db, key):
    return ls.fields(db, listing(db).id)[key]


async def start_honey(turn, price_text="ba trăm nghìn"):
    await turn(f"Cô muốn bán mật ong rừng {price_text} một chai")
    _, said = await turn("đúng")          # tên
    return said


# ---------------- S-E1 .. S-E8 ----------------

async def test_SE1_confusable_low_confidence(db, turn):
    await turn("Cô muốn bán mật ong rừng")
    await turn("đúng")                      # tên -> hỏi ảnh
    s = sessions.get(1)
    s.awaiting = ("field", listing(db).id, "price")
    _, said = await turn("bảy trăm", confidence=0.7)
    assert "BẢY, số bảy, không phải ba" in said
    assert "bảy trăm nghìn đồng" in said
    assert blocked(db, "CONFUSABLE_NUMBER", 1)


async def test_SE2_assumed_unit(db, turn):
    said = await start_honey(turn, "ba trăm")
    assert "ba trăm nghìn đồng" in said and "NGHÌN" in said
    assert blocked(db, "ASSUMED_UNIT", 1)


async def test_SE3_image_mismatch(db, turn):
    await start_honey(turn)
    await turn("đúng")                                       # giá -> hỏi ảnh
    _, said = await turn(image=demo_image(db, "honey_1x500.jpg"))
    assert "một chai thủy tinh nhỏ" in said
    await turn("đúng")                                       # ảnh đúng hàng -> hỏi dung tích
    _, said = await turn("một lít")
    assert "Trong ảnh tôi thấy chai cỡ nửa lít" in said
    assert blocked(db, "IMAGE_MISMATCH", 3)
    _, said = await turn("nửa lít")                          # sửa
    assert "Mỗi chai là nửa lít" in said
    await turn("đúng")
    assert field(db, "volume_ml").state == FieldState.CONFIRMED and field(db, "volume_ml").value == "500"


async def test_SE4_price_outlier(db, turn):
    said = await start_honey(turn, "ba mươi lăm nghìn")
    assert "thấp hơn nhiều" in said and "ba trăm năm mươi nghìn đồng" in said
    assert blocked(db, "PRICE_OUTLIER_LOW", 2)
    _, said = await turn("ba trăm năm mươi nghìn")
    assert field(db, "price").value == "350000"


async def test_SE5_weak_yes_on_price(db, turn):
    await start_honey(turn)
    _, said = await turn("ừ")
    assert "nói 'đúng' giúp tôi" in said
    assert field(db, "price").state != FieldState.CONFIRMED
    await turn("đúng")
    assert field(db, "price").state == FieldState.CONFIRMED


async def test_SE6_rubber_stamp(db, turn):
    await turn("Cô muốn bán mật ong rừng ba trăm nghìn một chai")
    s = sessions.get(1)
    for _ in range(3):   # 3 xác nhận ĐỎ liên tiếp, mỗi lần < 2 giây
        log_confirmation(db, s.pending, "confirmed", "đúng", 400)
    await turn("đúng", latency_ms=400)                       # tên (ĐỎ, chữ) -> không hỏi mở
    _, said = await turn("đúng", latency_ms=400)             # giá -> nghi gật đầu theo quán tính
    assert "nhắc lại giúp tôi" in said and "bao nhiêu tiền" in said
    assert field(db, "price").state != FieldState.CONFIRMED
    _, said = await turn("hai trăm nghìn")                   # lệch với 300.000 đã "xác nhận"
    assert blocked(db, "RUBBER_STAMP", 4)
    assert field(db, "price").value == "200000" and field(db, "price").state != FieldState.CONFIRMED


async def test_SE7_unsourced_and_banned_claims(db):
    seller = db.get(Seller, 1)
    lst = ls.start_listing(db, seller, "honey")
    ls.set_field(db, seller, lst, "name", "mật ong rừng")
    f = ls.fields(db, lst.id)["name"]
    f.state = FieldState.CONFIRMED
    db.add(f)
    db.commit()
    r = ls.save_draft(db, seller, lst, "Mật ong nguyên chất 100%", "Mật ong nguyên chất 100%. Mật ong rừng [name].")
    assert blocked(db, "UNSOURCED_SENTENCE", 3) and blocked(db, "BANNED_CLAIM", 3)
    assert "nguyên chất" not in lst.public_description and "nguyên chất" not in lst.title
    assert lst.public_description == "Mật ong rừng."


async def test_SE8_publish_blocked_when_origin_unconfirmed(db):
    seller = db.get(Seller, 1)
    lst = ls.start_listing(db, seller, "honey")
    for k, v in {"name": "Mật ong", "price": "300000", "volume_ml": "500", "stock": "8", "container": "chai thủy tinh",
                 "harvest_time": "tháng 3"}.items():
        f = ls.fields(db, lst.id)[k]
        f.value, f.state = v, FieldState.CONFIRMED
        db.add(f)
    db.commit()
    r = ls.request_publish(db, seller, lst)
    assert not r["ok"] and r["confirmation"] is None
    assert ("NOT_CONFIRMED", "origin") in [(w["code"], w["params"]["detail"]) for w in r["warnings"]]
    assert lst.status == "drafting"
    assert blocked(db, "NOT_CONFIRMED", 5)


# ---------------- đơn hàng ----------------

def honey_order(db, qty=2, status="accepted"):
    seller = db.get(Seller, 1)
    honey = db.get(Listing, listing_key_map(db)["honey_mint"])
    honey.stock = 10
    db.add(honey)
    o = simulator.spawn_order(db, seller, honey, qty, "Nguyễn Thị Lan", "Hà Nội", 2)
    o.status = status
    db.add(o)
    db.commit()
    sessions.get(1).active_order_id = o.id
    return o


async def test_SO1_packing_mismatch(db, turn):
    o = honey_order(db)
    _, said = await turn(image=demo_image(db, "honey_1x500.jpg"), purpose="packing_check")
    assert "Đơn cần hai chai, tôi chỉ thấy một chai" in said
    assert blocked(db, "PACKING_MISMATCH", 3)
    _, said = await turn("đóng gói xong")
    db.refresh(o)
    assert o.status == "accepted" and "Chưa kiểm tra hàng" in said
    _, said = await turn(image=demo_image(db, "honey_2x500.jpg"), purpose="packing_check")
    assert "Đóng xong thì nói" in said
    await turn("đóng gói xong")
    await turn("đúng")
    db.refresh(o)
    assert o.status == "packed"


async def test_SO2_shipped_without_tracking(db, turn):
    o = honey_order(db, status="packed")
    _, said = await turn("đã gửi rồi")
    assert "Chưa có mã gửi hàng" in said
    assert blocked(db, "NO_TRACKING", 5)
    db.refresh(o)
    assert o.status == "packed"
    _, said = await turn(image=demo_image(db, "receipt_spx.jpg"), purpose="receipt")
    assert "nhóm một: S-P-X-V" in said and "kết thúc bằng năm-sáu-bảy-tám" in said
    _, said = await turn("đúng")                       # hai bước: "đúng" chưa đủ
    db.refresh(o)
    assert o.status == "packed" and "đã gửi rồi" in said
    await turn("đã gửi rồi")
    db.refresh(o)
    assert o.status == "shipped" and o.tracking_code == "SPXV12345678"


async def test_SO3_silence_is_not_consent(db, turn):
    o = honey_order(db, qty=1, status="new")
    await turn("nhận đơn")                              # chưa đọc chi tiết -> đọc rồi hỏi
    _, said = await turn(typ="timeout")
    assert "còn đó không" in said
    _, said = await turn(typ="timeout")
    assert "Khi nào cô sẵn sàng" in said
    db.refresh(o)
    assert o.status == "new" and sessions.get(1).pending is None


async def test_SB1_unknown_question_goes_to_seller(db, turn):
    seller = db.get(Seller, 1)
    honey = db.get(Listing, listing_key_map(db)["honey_mint"])
    for old in db.exec(select(BuyerMessage)).all():   # bỏ câu hỏi mẫu để câu mới là câu chờ đầu tiên
        db.delete(old)
    db.commit()
    msg, _ = simulator.spawn_buyer_message(db, seller, honey, "Mật ong có pha đường không shop?", "Khách ở Đà Nẵng")
    assert msg.status == "waiting_seller" and msg.answer.startswith("Dạ shop đang kiểm tra")
    _, said = await turn("khách hỏi gì")
    assert "pha đường" in said
    _, said = await turn("Không pha gì hết, mật nhà nuôi lấy luôn")
    assert "Tôi sẽ trả lời khách là: Dạ," in said
    await turn("gửi đi")
    db.refresh(msg)
    assert msg.status == "answered_seller"
    msg2, _ = simulator.spawn_buyer_message(db, seller, honey, "mật ong có pha đường không vậy", "Khách khác")
    assert msg2.status == "answered_auto"   # đã học thành FAQ


async def test_scam_message_flagged(db):
    seller = db.get(Seller, 1)
    honey = db.get(Listing, listing_key_map(db)["honey_mint"])
    msg, ev = simulator.spawn_buyer_message(db, seller, honey, "Chị gửi hàng trước đi, em chuyển khoản qua Zalo, đọc mã OTP nhé", "Lạ")
    assert msg.status == "scam_flagged" and any(e["type"] == "notify" and e["kind"] == "warning" for e in ev)


async def test_continue_command_is_not_a_field_value(db, turn):
    await turn(button="cat:honey")
    _, said = await turn("làm tiếp")
    assert "tên là gì" in said
    assert field(db, "name").value is None


# ---------------- luồng đầy đủ ----------------

async def test_full_listing_flow(db, turn):
    _, said = await turn("Cô muốn bán mật ong rừng ba trăm nghìn một chai")
    assert "Tên sản phẩm là: Mật ong rừng" in said
    _, said = await turn("đúng")
    assert "ba trăm nghìn đồng" in said and "ba tờ một trăm nghìn" in said
    _, said = await turn("đúng")
    assert "chụp một ảnh" in said
    _, said = await turn(image=demo_image(db, "honey_1x500_dark.jpg"))
    assert "Ảnh hơi tối" in said
    _, said = await turn(image=demo_image(db, "honey_1x500.jpg"))
    await turn("đúng")
    _, said = await turn("nửa lít")
    assert "nửa lít" in said
    _, said = await turn("đúng")
    assert "bao nhiêu chai" in said
    await turn("tám chai")
    _, said = await turn("đúng")
    assert "lấy ở đâu" in said
    await turn("ở Hà Giang")
    _, said = await turn("đúng")
    assert "thủy tinh" in said
    await turn("thủy tinh")
    await turn("đúng")
    await turn("tháng ba")
    _, said = await turn("đúng")
    assert "Bảo quản" in said
    _, said = await turn("bỏ qua")
    assert "Cô còn khoảng" in said and "tiền hộp gói" in said and "đăng đi" in said
    _, said = await turn("ừ")
    assert "'đăng đi'" in said and listing(db).status == "ready"
    _, said = await turn("đăng đi")
    lst = listing(db)
    assert lst.status == "pending_publish" and "rút lại" in said
    assert "Hà Giang" in lst.public_description and "Không dùng cho trẻ dưới 1 tuổi." in lst.public_description
    _, said = await turn("rút lại")
    db.refresh(lst)
    assert lst.status == "drafting"
