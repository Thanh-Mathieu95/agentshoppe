"""Phát triển bán hàng: tối đa 1 gợi ý, có số liệu, không tự áp dụng (mục 12)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from app import catalog
from app.confirm import templates as tp
from app.confirm.engine import ConfirmationRequest
from app.events import card, res
from app.i18n.vi import t
from app.models import BuyerMessage, GrowthSuggestion, Listing, Order, OrderItem, Risk, Seller
from app.services import listings as ls
from app.services import orders as osv
from app.services import pricing, support
from app.validators.numbers import number_to_words
from app.validators.sources import BANNED_CLAIMS


def sold_last_7d(db: Session, listing_id: int) -> int:
    since = datetime.now() - timedelta(days=7)
    rows = db.exec(select(OrderItem, Order).where(OrderItem.order_id == Order.id, OrderItem.listing_id == listing_id,
                                                  Order.created_at >= since, Order.status != "cancelled")).all()
    return sum(it.quantity for it, _ in rows)


def _declined_recently(db: Session, seller_id: int, kind: str) -> bool:
    since = datetime.now() - timedelta(days=7)
    return db.exec(select(GrowthSuggestion).where(GrowthSuggestion.seller_id == seller_id, GrowthSuggestion.kind == kind,
                                                  GrowthSuggestion.status == "declined",
                                                  GrowthSuggestion.updated_at >= since)).first() is not None


def _candidates(db: Session, seller: Seller) -> list[dict]:
    h = seller.honorific
    out = []
    live = list(db.exec(select(Listing).where(Listing.seller_id == seller.id, Listing.status.in_(["published", "hidden"]))).all())

    # 1. khách chờ trả lời (rủi ro thấp nhất)
    late = support.waiting_over(db, seller.id, 12)
    if late:
        out.append({"kind": "answer_pending", "message": f"Có {number_to_words(len(late))} khách đang chờ {h} trả lời. Trả lời nhanh giúp bán được hơn.",
                    "evidence": {"waiting": len(late), "oldest_hours": int((datetime.now() - late[0].created_at).total_seconds() // 3600)},
                    "action": {"type": "answer", "message_id": late[0].id}, "risk": None})
    # 2. sắp hết hàng
    for lst in live:
        if lst.stock is not None and lst.stock <= seller.low_stock_threshold:
            sold = sold_last_7d(db, lst.id)
            out.append({"kind": "restock",
                        "message": f"{ls.name_of(db, lst)} còn {number_to_words(lst.stock) if lst.stock else 'không'} {ls.container(lst)}. "
                                   f"Tuần trước {h} bán {number_to_words(sold) if sold else 'không'} {ls.container(lst)}. {h.capitalize()} có thêm hàng không?",
                        "evidence": {"stock": lst.stock, "sold_7d": sold, "threshold": seller.low_stock_threshold},
                        "action": {"type": "update_stock", "listing_id": lst.id}, "risk": "red"})
    # 3. từ khóa người mua hay tìm (chỉ khi từ khóa đúng với dữ liệu đã xác nhận)
    terms = catalog.analytics().get("buyer_search_terms", {})
    for lst in live:
        title = (lst.title or "").lower()
        facts = " ".join((f.value or "").lower() for f in ls.fields(db, lst.id).values() if f.state.value == "confirmed")
        label = catalog.category(lst.category)["label"].lower()
        for term in terms.get(lst.category, []):
            extra = term.lower().replace(label, "").strip()
            if term.lower() in title or not extra or any(b in term.lower() for b in BANNED_CLAIMS):
                continue
            if extra in facts and extra not in title:
                new_title = f"{lst.title} {extra.title()}" if extra.title() not in (lst.title or "") else lst.title
                out.append({"kind": "title_keywords",
                            "message": f"Người mua hay tìm '{term}'. {h.capitalize()} có muốn thêm '{extra}' vào tên {ls.name_of(db, lst)} không?",
                            "evidence": {"term": term, "source": "buyer_search_terms"},
                            "action": {"type": "title", "listing_id": lst.id, "new_title": new_title}, "risk": "yellow"})
                break
    # 4. giá cao hơn phần lớn và ít đơn
    for lst in live:
        fs = ls.fields(db, lst.id)
        if not fs.get("price") or not fs["price"].value:
            continue
        price = int(fs["price"].value)
        pc = pricing.price_check(lst.category, price)
        sold = sold_last_7d(db, lst.id)
        if pc["percentile"] >= 0.8 and sold <= 1:
            target = int(round(pc["median"] * 1.1, -4))
            pay = pricing.payout(lst.category, target)["payout"]
            out.append({"kind": "price_position",
                        "message": f"Giá {ls.name_of(db, lst)} cao hơn phần lớn shop khác. Giảm còn {tp.money_short(target)} thì {h} vẫn nhận khoảng {tp.money_short(pay)}.",
                        "evidence": {"percentile": pc["percentile"], "sold_7d": sold, "median": pc["median"]},
                        "action": {"type": "price", "listing_id": lst.id, "new_price": target}, "risk": "red"})
    # 5. hay mua cùng nhau
    cats = {lst.category: lst for lst in live}
    for pair in catalog.analytics().get("co_purchase_pairs", []):
        if pair["a"] in cats and pair["b"] in cats:
            out.append({"kind": "bundle",
                        "message": f"Khách hay mua {catalog.category(pair['a'])['label'].lower()} cùng {catalog.category(pair['b'])['label'].lower()}. {h.capitalize()} có muốn bán gói cả hai không?",
                        "evidence": {"share": pair["share"], "note": pair["note"]},
                        "action": {"type": "bundle", "a": cats[pair["a"]].id, "b": cats[pair["b"]].id}, "risk": "red"})
    # 6. theo mùa
    month = date.today().month
    for cat, seasons in catalog.analytics().get("season_calendar", {}).items():
        for s in seasons:
            lst = next((l for l in live if l.category == cat and l.status == "hidden"), None)
            if lst and month in s["months"]:
                out.append({"kind": "seasonal",
                            "message": f"Đang mùa {s['name']}. {h.capitalize()} muốn đăng lại tin {ls.name_of(db, lst)} không?",
                            "evidence": {"months": s["months"]}, "action": {"type": "republish", "listing_id": lst.id}, "risk": "red"})
    return out


def get_suggestion(db: Session, seller: Seller) -> GrowthSuggestion | None:
    for c in _candidates(db, seller):
        if _declined_recently(db, seller.id, c["kind"]):
            continue
        existing = db.exec(select(GrowthSuggestion).where(GrowthSuggestion.seller_id == seller.id, GrowthSuggestion.kind == c["kind"],
                                                          GrowthSuggestion.status == "proposed")).first()
        if existing:
            existing.message, existing.evidence, existing.action = c["message"], c["evidence"], c["action"]
            db.add(existing)
            db.commit()
            return existing
        s = GrowthSuggestion(seller_id=seller.id, kind=c["kind"], message=c["message"], evidence=c["evidence"], action=c["action"])
        db.add(s)
        db.commit()
        return s
    return None


def suggestion_res(seller: Seller, s: GrowthSuggestion | None) -> dict:
    if not s:
        return res(True, say=t("suggestion_none", seller.honorific))
    return res(True, say=t("suggestion_ask", seller.honorific, text=s.message), data={"suggestion_id": s.id, "kind": s.kind},
               events=[card(kind="suggestion", big="💡", text=s.message, suggestion_id=s.id, evidence=s.evidence)])


def respond(db: Session, seller: Seller, s: GrowthSuggestion, decision: str) -> dict:
    h = seller.honorific
    if decision == "decline":
        s.status = "declined"
        s.updated_at = datetime.now()
        db.add(s)
        db.commit()
        return res(True, say=t("suggestion_declined", h))
    if decision == "later":
        s.status = "expired"
        db.add(s)
        db.commit()
        return res(True, say=t("suggestion_later", h))
    s.status = "accepted"
    db.add(s)
    db.commit()
    a = s.action
    if a["type"] == "answer":
        msg = db.get(BuyerMessage, a["message_id"])
        r = support.question_prompt(seller, msg)
        r["data"]["next"] = ("seller_reply", msg.id)
        return r
    if a["type"] == "update_stock":
        lst = db.get(Listing, a["listing_id"])
        return res(True, say=t("restock_ask_number", h, container=ls.container(lst)), data={"next": ("restock", lst.id)})
    if a["type"] == "title":
        lst = db.get(Listing, a["listing_id"])
        req = ConfirmationRequest(seller_id=seller.id, subject_ref=f"listing:{lst.id}:title", kind="action", risk=Risk.YELLOW,
                                  prompt_text=t("title_prompt", h, title=a["new_title"]), action_phrase="làm đi",
                                  card={"kind": "confirm", "big": "✎", "text": a["new_title"], "risk": "yellow"},
                                  payload={"title": a["new_title"]})
        return res(True, confirmation=req)
    if a["type"] == "price":
        lst = db.get(Listing, a["listing_id"])
        return ls.request_price_change(db, seller, lst, str(a["new_price"]))
    if a["type"] == "republish":
        lst = db.get(Listing, a["listing_id"])
        req = ConfirmationRequest(seller_id=seller.id, subject_ref=f"listing:{lst.id}:republish", kind="action", risk=Risk.RED,
                                  prompt_text=t("seasonal_prompt", h, name=ls.name_of(db, lst)), two_step=True, action_phrase="đăng đi",
                                  card={"kind": "confirm", "big": "↻", "text": f"Đăng lại {ls.name_of(db, lst)}", "risk": "red", "two_step": True})
        return res(True, confirmation=req)
    return res(True, say=t("bundle_note", h))


def daily_briefing(db: Session, seller: Seller) -> dict:
    h = seller.honorific
    start = datetime.combine(date.today(), datetime.min.time())
    today = list(db.exec(select(Order).where(Order.seller_id == seller.id, Order.created_at >= start,
                                             Order.status != "cancelled")).all())
    payout = sum(o.seller_payout for o in today)
    tomorrow_end = start + timedelta(days=2)
    to_ship = [o for o in osv.open_orders(db, seller.id) if o.ship_by < tomorrow_end]
    waiting = support.waiting(db, seller.id)
    sug = get_suggestion(db, seller)
    text = t("briefing", h,
             n_orders=number_to_words(len(today)) if today else "không",
             payout=tp.money_spoken(payout) if payout else "chưa có tiền",
             to_ship=t("briefing_to_ship", h, n=number_to_words(len(to_ship)), earliest=tp.deadline_spoken(to_ship[0].ship_by)) if to_ship else "",
             questions=t("briefing_questions", h, n=number_to_words(len(waiting))) if waiting and not (sug and sug.kind == "answer_pending") else "",
             suggestion=t("briefing_suggestion", h, text=sug.message) if sug else "")
    cards = [
        card(kind="stat", big=str(len(today)), text="Đơn hôm nay", icon="📦"),
        card(kind="stat", big=tp.money_digits(payout), text="Tiền nhận", icon="💵", visual=f"notes:{tp.notes_visual(payout)}" if payout else None),
        card(kind="stat", big=str(len(to_ship) + len(waiting)), text="Việc cần làm", icon="✅",
             detail=f"{len(to_ship)} đơn cần gửi, {len(waiting)} khách chờ"),
    ]
    if sug:
        cards.append(card(kind="suggestion", big="💡", text=sug.message, suggestion_id=sug.id, evidence=sug.evidence))
    return res(True, say=text, data={"orders": len(today), "payout": payout, "to_ship": len(to_ship), "questions": len(waiting),
                                     "suggestion_id": sug.id if sug else None}, events=cards)
