"""Engine, phiên DB, tạo bảng và nạp dữ liệu demo. Chạy: python -m app.db --seed"""
import hashlib
import sys
from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine, select

from app import catalog, demo_photos
from app.config import DATABASE_URL, UPLOAD_DIR
from app import product_art
from app.models import (FAQ, BuyerMessage, FieldState, Image, Listing, ListingField, Order, OrderItem, Review, Risk,
                        Seller, Source)
from app.services.pricing import order_payout
from app.validators.sources import strip_tags

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def get_session() -> Session:
    return Session(engine, expire_on_commit=False)


def init_db(drop: bool = False) -> None:
    if drop:
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as c:   # DB cũ: thêm cột mới (create_all không sửa bảng đã có)
        if "theme" not in [r[1] for r in c.exec_driver_sql("PRAGMA table_info(seller)")]:
            c.exec_driver_sql("ALTER TABLE seller ADD COLUMN theme JSON DEFAULT '{}'")


def seed(db: Session) -> Seller:
    data = catalog.seed()
    seller = Seller(**data["seller"])
    db.add(seller)
    db.commit()
    now = datetime.now()
    keymap: dict[str, Listing] = {}
    for item in data["listings"]:
        keymap[item["key"]] = _seed_listing(db, seller, item, now)
    for shop in data.get("other_shops", []):
        other = Seller(name=shop["name"], shop_name=shop["shop_name"], avatar=shop["avatar"], region=shop["region"],
                       followers=shop.get("followers", 0), shipping_days=["mon", "wed", "fri"])
        db.add(other)
        db.commit()
        for item in shop["listings"]:
            _seed_listing(db, other, {**item, "status": "published"}, now)
    for faq in data["faqs"]:
        db.add(FAQ(listing_id=keymap[faq["listing"]].id, question=faq["question"], answer=faq["answer"], approved_by_seller=True))
    for o in data["orders"]:
        lst = keymap[o["listing"]]
        price = int(_field_value(db, lst.id, "price"))
        created = now - timedelta(days=o["created_days_ago"])
        order = Order(seller_id=seller.id, external_id=o["external_id"], status=o["status"], buyer_name=o["buyer_name"],
                      buyer_province=o["buyer_province"], seller_payout=order_payout(price, o["qty"]),
                      ship_by=(now + timedelta(days=o["ship_by_days"])).replace(hour=17, minute=0, second=0, microsecond=0),
                      tracking_code=o.get("tracking_code"), created_at=created,
                      packing_check_passed=o["status"] in ("packed", "shipped", "delivered"))
        db.add(order)
        db.commit()
        db.add(OrderItem(order_id=order.id, listing_id=lst.id, quantity=o["qty"]))
    for m in data["buyer_messages"]:
        db.add(BuyerMessage(seller_id=seller.id, listing_id=keymap[m["listing"]].id, buyer_name=m["buyer_name"],
                            text=m["text"], status=m["status"], created_at=now - timedelta(hours=m.get("hours_ago", 0))))
    db.commit()
    return seller


def _seed_listing(db: Session, seller: Seller, item: dict, now: datetime) -> Listing:
    lst = Listing(seller_id=seller.id, category=item["category"], status=item["status"], title=item["title"],
                  description=item["description"], draft_raw=item["description"], views_7d=item.get("views_7d", 0),
                  price_checked=True, stock=int(item["fields"]["stock"]), sold=item.get("sold", 0),
                  rating=item.get("rating", 0), list_price=item.get("list_price"))
    lst.public_description = strip_tags(item["description"])
    db.add(lst)
    db.commit()
    for tpl in catalog.category(item["category"])["fields"]:
        val = item["fields"].get(tpl["key"])
        db.add(ListingField(listing_id=lst.id, key=tpl["key"], value=val, unit=tpl.get("unit"),
                            risk=Risk(tpl["risk"]), state=FieldState.CONFIRMED if val else FieldState.EMPTY,
                            source=Source.VOICE if val else None, confirmed_at=now if val else None,
                            raw_utterance=val, history=[val] if val else []))
    key = f"{item['category']}_{item.get('variant', '')}_{item.get('art', '')}".replace(" ", "_")
    path = UPLOAD_DIR / "art" / f"{hashlib.md5(key.encode()).hexdigest()[:12]}.jpg"
    if not path.exists():
        product_art.render(item["category"], item.get("art", ""), path, item.get("variant", ""), seed=len(key))
    img = Image(owner_type="listing", owner_id=lst.id, path=str(path), accepted=True,
                description=item["title"], quality={"bright": 0.8, "sharp": 2.0})
    db.add(img)
    db.commit()
    lst.image_ids = [img.id]
    for stars, who, text in item.get("reviews", []):
        db.add(Review(listing_id=lst.id, buyer_name=who, stars=stars, text=text,
                      created_at=now - timedelta(days=stars + len(text) % 9)))
    db.add(lst)
    db.commit()
    return lst


def listing_key_map(db: Session) -> dict[str, int]:
    """Ánh xạ key trong demo_seed -> id (theo thứ tự tạo)."""
    ids = [l.id for l in db.exec(select(Listing).order_by(Listing.id)).all()]
    return {item["key"]: ids[i] for i, item in enumerate(catalog.seed()["listings"]) if i < len(ids)}


def _field_value(db: Session, listing_id: int, key: str) -> str | None:
    f = db.exec(select(ListingField).where(ListingField.listing_id == listing_id, ListingField.key == key)).first()
    return f.value if f else None


def reset() -> None:
    init_db(drop=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    demo_photos.generate()
    catalog.load.cache_clear()
    with get_session() as db:
        seed(db)


if __name__ == "__main__":
    if "--seed" in sys.argv:
        reset()
        print("Đã tạo DB và nạp dữ liệu demo.")
    else:
        init_db()
