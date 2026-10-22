"""Sàn thương mại giả lập: danh mục, tìm kiếm, chi tiết, giỏ/đặt hàng, theo dõi đơn, chat (mục 16, mở rộng)."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app import catalog
from app.db import get_session
from app.mock_shopee import simulator
from app.models import FAQ, BuyerMessage, FieldState, Listing, Order, OrderItem, Review, Seller
from app.services import listings as ls
from app.services import notifier
from app.services import orders as osv
from app.services.pricing import order_payout

router = APIRouter(prefix="/mock/shopee", tags=["mock-shopee"])

CAT_ICON = {"honey": "🍯", "tea": "🍵", "handicraft": "🧶", "candle": "🕯️", "dried_food": "🥩"}
BUYER_STATUS = {"new": "Chờ xác nhận", "accepted": "Chờ lấy hàng", "packed": "Đã đóng gói", "shipped": "Đang giao",
                "delivered": "Đã giao", "cancelled": "Đã hủy", "dispute": "Đang khiếu nại"}
STEPS = ["new", "accepted", "packed", "shipped", "delivered"]


def _price(db, lst: Listing) -> int | None:
    f = ls.fields(db, lst.id).get("price")
    return int(f.value) if f and f.value else None


def _img(lst: Listing) -> str | None:
    return f"/api/images/{lst.image_ids[0]}/file" if lst.image_ids else None


def summary(db, lst: Listing, seller: Seller | None = None) -> dict:
    seller = seller or db.get(Seller, lst.seller_id)
    price = _price(db, lst)
    lp = lst.list_price if lst.list_price and price and lst.list_price > price else None
    return {"id": lst.id, "title": lst.title or ls.name_of(db, lst), "price": price, "list_price": lp,
            "discount": round((1 - price / lp) * 100) if lp else 0, "sold": lst.sold, "rating": lst.rating,
            "image": _img(lst), "images": [f"/api/images/{i}/file" for i in (lst.image_ids or [])],
            "category": lst.category, "category_label": catalog.category(lst.category)["label"],
            "icon": CAT_ICON.get(lst.category), "stock": lst.stock,
            "shop": {"id": seller.id, "name": seller.shop_name or seller.name, "region": seller.region,
                     "avatar": seller.avatar, "assistant": seller.uses_assistant}}


def public_listing(db, lst: Listing) -> dict:
    return {**summary(db, lst), "description": lst.public_description, "status": lst.status,
            "visual": catalog.category(lst.category).get("visual")}


@router.get("/categories")
def categories():
    with get_session() as db:
        rows = db.exec(select(Listing).where(Listing.status == "published")).all()
        return [{"key": k, "label": v["label"], "icon": CAT_ICON.get(k), "count": sum(1 for l in rows if l.category == k)}
                for k, v in catalog.categories().items()]


@router.get("/catalog")
def catalog_list(q: str | None = None, category: str | None = None, sort: str = "popular", shop: int | None = None):
    with get_session() as db:
        stmt = select(Listing).where(Listing.status == "published")
        if category:
            stmt = stmt.where(Listing.category == category)
        if shop:
            stmt = stmt.where(Listing.seller_id == shop)
        rows = [summary(db, l) for l in db.exec(stmt).all()]
        if q:
            words = q.lower().split()
            rows = [r for r in rows if all(w in (r["title"] + " " + r["shop"]["name"] + " " + (r["shop"]["region"] or "")).lower() for w in words)]
        key = {"popular": lambda r: -r["sold"], "new": lambda r: -r["id"], "price_asc": lambda r: r["price"] or 0,
               "price_desc": lambda r: -(r["price"] or 0), "rating": lambda r: -r["rating"]}.get(sort, lambda r: -r["sold"])
        return sorted(rows, key=key)


@router.get("/products/{listing_id}")
def product(listing_id: int):
    with get_session() as db:
        lst = db.get(Listing, listing_id)
        if not lst or lst.status not in ("published",):
            raise HTTPException(404, "Sản phẩm không còn bán")
        seller = db.get(Seller, lst.seller_id)
        specs = [{"label": ls.label_of(lst, f.key).capitalize(), "value": ls.short_value(lst, f.key, f.value), "key": f.key}
                 for f in ls.fields(db, lst.id).values()
                 if f.state == FieldState.CONFIRMED and f.value and f.key not in ("name", "price", "stock")]
        reviews = db.exec(select(Review).where(Review.listing_id == lst.id).order_by(Review.id.desc())).all()
        faqs = db.exec(select(FAQ).where(FAQ.listing_id == lst.id, FAQ.approved_by_seller == True)).all()  # noqa: E712
        shop_count = len(db.exec(select(Listing).where(Listing.seller_id == seller.id, Listing.status == "published")).all())
        return {**summary(db, lst, seller), "description": lst.public_description, "specs": specs,
                "reviews": [{"buyer": r.buyer_name, "stars": r.stars, "text": r.text, "at": r.created_at.date().isoformat()} for r in reviews],
                "faqs": [{"q": f.question, "a": f.answer} for f in faqs],
                "shop": {**summary(db, lst, seller)["shop"], "followers": seller.followers, "products": shop_count},
                "fees_note": catalog.fees()["note"]}


@router.get("/shops/{seller_id}")
def shop(seller_id: int):
    with get_session() as db:
        s = db.get(Seller, seller_id)
        if not s:
            raise HTTPException(404)
        rows = db.exec(select(Listing).where(Listing.seller_id == s.id, Listing.status == "published")).all()
        items = [summary(db, l, s) for l in rows]
        rated = [l.rating for l in rows if l.rating]
        return {"id": s.id, "name": s.shop_name or s.name, "owner": s.name, "region": s.region, "avatar": s.avatar,
                "followers": s.followers, "assistant": s.uses_assistant, "rating": round(sum(rated) / len(rated), 1) if rated else None,
                "intro": s.intro, "color": (s.theme or {}).get("color"),
                "banner": f"/api/images/{s.theme['banner_id']}/file" if (s.theme or {}).get("banner_id") else None,
                "products": items}


# ---------------- đặt hàng ----------------

class CartItem(BaseModel):
    listing_id: int
    qty: int = Field(ge=1, le=99)


class CheckoutIn(BaseModel):
    buyer_key: str = Field(min_length=4, max_length=64)
    buyer_name: str = Field(min_length=2, max_length=60)
    phone: str = Field(min_length=8, max_length=15)
    province: str = Field(min_length=2, max_length=40)
    address: str = Field(min_length=3, max_length=160)
    items: list[CartItem] = Field(min_length=1, max_length=30)


@router.post("/checkout")
async def checkout(body: CheckoutIn):
    pushes: list[tuple[int, list[dict]]] = []
    created = []
    with get_session() as db:
        by_seller: dict[int, list[tuple[Listing, int]]] = {}
        for it in body.items:
            lst = db.get(Listing, it.listing_id)
            if not lst or lst.status != "published":
                raise HTTPException(409, f"Sản phẩm #{it.listing_id} không còn bán")
            if (lst.stock or 0) < it.qty:
                raise HTTPException(409, f"“{lst.title}” chỉ còn {lst.stock or 0}")
            by_seller.setdefault(lst.seller_id, []).append((lst, it.qty))
        for seller_id, lines in by_seller.items():
            seller = db.get(Seller, seller_id)
            payout = sum(order_payout(_price(db, l), q) for l, q in lines)
            o = Order(seller_id=seller_id, external_id=f"SPE-{datetime.now():%m%d}{len(created) + 1}{body.buyer_key[-3:].upper()}",
                      buyer_name=body.buyer_name, buyer_province=body.province, seller_payout=payout,
                      ship_by=(datetime.now() + timedelta(days=2)).replace(hour=17, minute=0, second=0, microsecond=0),
                      buyer_phone=body.phone, buyer_address=body.address, buyer_key=body.buyer_key)
            db.add(o)
            db.commit()
            for l, q in lines:
                db.add(OrderItem(order_id=o.id, listing_id=l.id, quantity=q))
                l.sold += q
                db.add(l)
            db.commit()
            created.append(o.id)
            if seller.uses_assistant:
                pushes.append((seller.id, simulator.ingest_order(db, seller, o)))
    for sid, ev in pushes:
        await notifier.push(sid, ev)
    return {"order_ids": created}


@router.get("/buyer/orders")
def buyer_orders(buyer_key: str):
    with get_session() as db:
        rows = db.exec(select(Order).where(Order.buyer_key == buyer_key).order_by(Order.id.desc())).all()
        out = []
        for o in rows:
            seller = db.get(Seller, o.seller_id)
            its = [{**summary(db, l, seller), "qty": it.quantity} for it, l in osv.items(db, o)]
            total = sum((i["price"] or 0) * i["qty"] for i in its)
            step = STEPS.index(o.status) if o.status in STEPS else -1
            out.append({"id": o.id, "code": o.external_id, "status": o.status, "status_text": BUYER_STATUS.get(o.status, o.status),
                        "step": step, "shop": its[0]["shop"] if its else None, "items": its, "total": total,
                        "tracking": o.tracking_code, "created_at": o.created_at.isoformat(timespec="minutes"),
                        "ship_by": o.ship_by.isoformat(timespec="minutes"), "cancel_reason": o.cancel_reason})
        return out


# ---------------- cho người bán / demo ----------------

@router.get("/listings")
def listings(seller_id: int = 1):
    with get_session() as db:
        rows = db.exec(select(Listing).where(Listing.seller_id == seller_id, Listing.status == "published")
                       .order_by(Listing.id.desc())).all()
        return [public_listing(db, l) for l in rows]


@router.get("/orders")
def orders(seller_id: int = 1):
    with get_session() as db:
        rows = db.exec(select(Order).where(Order.seller_id == seller_id).order_by(Order.id.desc())).all()
        return [osv.order_card(db, o) for o in rows]


class StatusIn(BaseModel):
    status: str


@router.post("/orders/{order_id}/status")
def order_status(order_id: int, body: StatusIn):
    """Phía sàn cập nhật (giao thành công...). Thao tác của người bán phải đi qua agent."""
    if body.status not in ("delivered", "dispute"):
        raise HTTPException(400, "Chỉ sàn được đặt delivered/dispute; thao tác người bán đi qua Confirmation Engine")
    with get_session() as db:
        o = db.get(Order, order_id)
        if not o or o.status not in ("shipped", "delivered"):
            raise HTTPException(409, "Đơn chưa gửi")
        o.status = body.status
        db.add(o)
        db.commit()
        return {"ok": True}


class MessageIn(BaseModel):
    listing_id: int
    text: str = Field(min_length=1, max_length=500)
    buyer_name: str = Field("Khách", max_length=60)


@router.get("/messages")
def messages(listing_id: int):
    with get_session() as db:
        rows = db.exec(select(BuyerMessage).where(BuyerMessage.listing_id == listing_id).order_by(BuyerMessage.id)).all()
        return [{"id": m.id, "buyer": m.buyer_name, "text": m.text, "answer": m.answer if m.status != "scam_flagged" else None,
                 "status": m.status, "by_assistant": m.status == "answered_auto",
                 "at": m.created_at.isoformat(timespec="minutes")} for m in rows]


@router.post("/messages")
async def post_message(body: MessageIn):
    with get_session() as db:
        lst = db.get(Listing, body.listing_id)
        if not lst:
            raise HTTPException(404)
        seller = db.get(Seller, lst.seller_id)
        msg, events = simulator.spawn_buyer_message(db, seller, lst, body.text, body.buyer_name)
        answer, status = msg.answer, msg.status
    if seller.uses_assistant:
        await notifier.push(seller.id, events)
    return {"id": msg.id, "answer": answer if status != "scam_flagged" else None, "status": status}


@router.get("/fees")
def fees():
    return catalog.fees()


@router.get("/market_prices")
def market_prices(category: str, q: str | None = None):
    return catalog.market(category)
