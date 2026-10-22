"""Sinh đơn và tin nhắn khách cho demo (theo kịch bản, không hẹn giờ ngẫu nhiên)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app import catalog
from app.agent import session as sessions
from app.models import BuyerMessage, Listing, Order, OrderItem, Seller
from app.services import listings as ls
from app.services import orders as osv
from app.services import support
from app.services.pricing import order_payout


def resolve_listing(db: Session, seller_id: int, ref: str | int | None) -> Listing | None:
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        return db.get(Listing, int(ref))
    q = select(Listing).where(Listing.seller_id == seller_id, Listing.status.in_(["published", "pending_publish"]))
    if isinstance(ref, str) and ref.startswith("latest_"):
        q = q.where(Listing.category == ref.split("_", 1)[1])
    return db.exec(q.order_by(Listing.id.desc())).first()


def spawn_order(db: Session, seller: Seller, listing: Listing, qty: int, buyer: str, province: str, ship_by_days: int) -> Order:
    price = int(ls.fields(db, listing.id)["price"].value)
    ship_by = (datetime.now() + timedelta(days=ship_by_days)).replace(hour=17, minute=0, second=0, microsecond=0)
    o = Order(seller_id=seller.id, external_id=f"SPE-{random.randint(2000, 9999)}", buyer_name=buyer, buyer_province=province,
              seller_payout=order_payout(price, qty), ship_by=ship_by)
    db.add(o)
    db.commit()
    db.add(OrderItem(order_id=o.id, listing_id=listing.id, quantity=qty))
    db.commit()
    return o


def ingest_order(db: Session, seller: Seller, order: Order) -> list[dict]:
    """OrderService.ingest: thông báo theo chế độ; câu báo đã đọc đủ chi tiết -> 'nhận đơn' được chấp nhận ngay."""
    s = sessions.get(seller.id)
    if not s.pending:
        s.active_order_id = order.id
        s.order_details_read = order.id
        s.awaiting = None
    return osv.new_order_events(db, seller, order)


def spawn_buyer_message(db: Session, seller: Seller, listing: Listing | None, text: str, buyer: str) -> tuple[BuyerMessage, list[dict]]:
    msg = BuyerMessage(seller_id=seller.id, listing_id=listing.id if listing else None, buyer_name=buyer, text=text)
    db.add(msg)
    db.commit()
    return msg, support.ingest(db, seller, msg)


def script() -> list[dict]:
    return catalog.demo_script()
