import httpx

from app.db import listing_key_map
from app.main import app
from app.models import Order


async def test_checkout_creates_order_for_seller_and_checks_stock(db):
    honey = listing_key_map(db)["honey_mint"]   # còn 2 chai
    body = {"buyer_key": "test-buyer", "buyer_name": "Lan", "phone": "0912345678", "province": "Hà Nội",
            "address": "12 Hàng Bạc", "items": [{"listing_id": honey, "qty": 3}]}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/mock/shopee/checkout", json=body)
        assert r.status_code == 409 and "chỉ còn 2" in r.json()["detail"]
        body["items"][0]["qty"] = 2
        r = await c.post("/mock/shopee/checkout", json=body)
        assert r.status_code == 200
        oid = r.json()["order_ids"][0]
        mine = (await c.get("/mock/shopee/buyer/orders", params={"buyer_key": "test-buyer"})).json()
        assert mine[0]["id"] == oid and mine[0]["status_text"] == "Chờ xác nhận"
        cat = (await c.get("/mock/shopee/catalog", params={"q": "thổ cẩm"})).json()
        assert cat and all(p["category"] == "handicraft" for p in cat)
    o = db.get(Order, oid)
    assert o.seller_id == 1 and o.status == "new"   # chưa trừ kho: người bán phải nhận đơn qua trợ lý
