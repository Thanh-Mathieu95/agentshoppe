"""Quản lý đơn hàng (mục 11, 6.3, 9.6)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from app import catalog
from app.confirm import templates as tp
from app.confirm.engine import ConfirmationRequest, log_blocked
from app.events import card, notify, res, speak
from app.i18n.vi import CANCEL_REASONS, DAY_NAMES, ORDER_STATUS, WEEKDAY_KEYS, t
from app.models import Image, Listing, Order, OrderItem, Risk, Seller
from app.services import listings as ls
from app.services import vision
from app.validators.numbers import number_to_words

OPEN = ("new", "accepted", "packed")


def items(db: Session, order: Order) -> list[tuple[OrderItem, Listing]]:
    rows = db.exec(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    return [(it, db.get(Listing, it.listing_id)) for it in rows]


def items_spoken(db: Session, order: Order) -> str:
    parts = []
    for it, lst in items(db, order):
        fs = ls.fields(db, lst.id)
        size = ""
        if fs.get("volume_ml") and fs["volume_ml"].value:
            size = " " + tp.volume_spoken(int(fs["volume_ml"].value))
        elif fs.get("weight_g") and fs["weight_g"].value:
            size = " " + tp.weight_spoken(int(fs["weight_g"].value))
        parts.append(f"{number_to_words(it.quantity)} {ls.container(lst)} {ls.name_of(db, lst).lower()}{size}")
    return ", ".join(parts)


def expected_items(db: Session, order: Order) -> list[dict]:
    out = []
    for it, lst in items(db, order):
        fs = ls.fields(db, lst.id)
        vol = fs.get("volume_ml")
        out.append({"name": ls.name_of(db, lst), "count": it.quantity, "volume_ml": int(vol.value) if vol and vol.value else None,
                    "container": ls.container(lst)})
    return out


def urgency(order: Order, now: datetime | None = None) -> str:
    h = tp.hours_left(order.ship_by, now)
    return "green" if h > 48 else "yellow" if h >= 24 else "red"


def order_card(db: Session, order: Order) -> dict:
    its = []
    for it, lst in items(db, order):
        its.append({"name": ls.name_of(db, lst), "qty": it.quantity, "container": ls.container(lst),
                    "image_id": (lst.image_ids or [None])[0], "visual": catalog.category(lst.category).get("visual")})
    actions = {"new": ["accept", "cancel"], "accepted": ["packing_check", "mark_packed", "cancel"],
               "packed": ["receipt", "mark_shipped"]}.get(order.status, [])
    return {"kind": "order", "order_id": order.id, "external_id": order.external_id, "buyer": order.buyer_name,
            "province": order.buyer_province, "items": its, "payout": order.seller_payout,
            "payout_big": tp.money_digits(order.seller_payout), "visual": f"notes:{tp.notes_visual(order.seller_payout)}",
            "ship_by": order.ship_by.isoformat(), "deadline": tp.deadline_spoken(order.ship_by),
            "urgency": urgency(order), "status": order.status, "status_text": ORDER_STATUS.get(order.status, order.status),
            "packing_ok": order.packing_check_passed or order.packing_override, "tracking": order.tracking_code,
            "actions": actions}


def open_orders(db: Session, seller_id: int) -> list[Order]:
    return list(db.exec(select(Order).where(Order.seller_id == seller_id, Order.status.in_(OPEN))
                        .order_by(Order.ship_by)).all())


def find(db: Session, seller: Seller, selector: str | None) -> Order | None:
    q = select(Order).where(Order.seller_id == seller.id)
    sel = (selector or "latest").strip().lower()
    if sel in ("latest", "mới nhất", "đơn mới nhất", ""):
        return db.exec(q.where(Order.status.in_(OPEN)).order_by(Order.created_at.desc(), Order.id.desc())).first()
    if sel.isdigit():
        return db.get(Order, int(sel))
    for o in db.exec(q.order_by(Order.id.desc())).all():
        name_bits = o.buyer_name.lower().split()
        if (sel in o.external_id.lower() or sel in o.buyer_name.lower() or sel in o.buyer_province.lower()
                or (name_bits and name_bits[-1] in sel.split())):
            return o
    return None


def new_order_events(db: Session, seller: Seller, order: Order) -> list[dict]:
    text = t("new_order", seller.honorific, buyer=order.buyer_name, province=order.buyer_province,
             items=items_spoken(db, order), payout=tp.money_spoken(order.seller_payout),
             deadline=tp.deadline_spoken(order.ship_by))
    return [notify("new_order", {"order_id": order.id, "text": text}, vibrate=[300, 150, 300]),
            speak(text, "normal"), card(**order_card(db, order))]


# ---------- truy vấn ----------

def list_orders(db: Session, seller: Seller, flt: str) -> dict:
    h = seller.honorific
    now = datetime.now()
    q = select(Order).where(Order.seller_id == seller.id)
    if flt == "today":
        start = datetime.combine(date.today(), datetime.min.time())
        today = list(db.exec(q.where(Order.created_at >= start)).all())
        pending = [o for o in open_orders(db, seller.id)]
        nearest = pending[0] if pending else None
        say = t("order_summary", h, total=number_to_words(len(today)) if today else "không",
                pending=t("order_summary_pending", h, n=number_to_words(len(pending))) if pending else "",
                nearest=t("order_summary_nearest", h, buyer=nearest.buyer_name, deadline=tp.deadline_spoken(nearest.ship_by)) if nearest else "")
        return res(True, say=say.strip(), data={"total": len(today), "pending": len(pending),
                                                 "order_ids": [o.id for o in pending]})
    if flt == "due_soon":
        due = [o for o in open_orders(db, seller.id) if tp.hours_left(o.ship_by, now) < 48]
        if not due:
            return res(True, say=t("orders_due_none", h), data={"order_ids": []})
        return res(True, say=t("orders_due_soon", h, n=number_to_words(len(due)), buyer=due[0].buyer_name,
                               deadline=tp.deadline_spoken(due[0].ship_by)), data={"order_ids": [o.id for o in due]})
    status = {"new": ["new"], "to_pack": ["accepted"], "to_ship": ["packed"], "all_open": list(OPEN)}.get(flt, list(OPEN))
    rows = list(db.exec(q.where(Order.status.in_(status)).order_by(Order.ship_by)).all())
    label = {"new": "mới", "to_pack": "cần đóng gói", "to_ship": "cần gửi", "all_open": "đang mở"}.get(flt, "")
    if not rows:
        return res(True, say=t("order_none", h), data={"order_ids": []})
    first = rows[0]
    say = t("orders_filter", h, n=number_to_words(len(rows)), label=label,
            first=f"Đơn đầu tiên của {first.buyer_name}, hạn {tp.deadline_spoken(first.ship_by)}.")
    return res(True, say=say, data={"order_ids": [o.id for o in rows]})


def order_detail(db: Session, seller: Seller, order: Order) -> str:
    return t("order_detail", seller.honorific, buyer=order.buyer_name, province=order.buyer_province,
             items=items_spoken(db, order), payout=tp.money_spoken(order.seller_payout),
             deadline=tp.deadline_spoken(order.ship_by), status=ORDER_STATUS.get(order.status, order.status))


def month_payout(db: Session, seller: Seller) -> str:
    start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.exec(select(Order).where(Order.seller_id == seller.id, Order.created_at >= start,
                                       Order.status != "cancelled")).all()
    total = sum(o.seller_payout for o in rows)
    return t("payout_month", seller.honorific, money=tp.money_spoken(total), n=number_to_words(len(rows)) if rows else "không")


# ---------- hành động (luôn qua xác nhận) ----------

def stock_check(db: Session, order: Order) -> tuple[bool, int, int, Listing | None]:
    for it, lst in items(db, order):
        have = lst.stock or 0
        if have < it.quantity:
            return False, it.quantity, have, lst
    return True, 0, 0, None


def can_order_action(db: Session, order: Order, action: str) -> str | None:
    if action == "accept":
        if order.status != "new":
            return "WRONG_STATE"
        ok, *_ = stock_check(db, order)
        if not ok:
            return "OUT_OF_STOCK"
    if action == "mark_packed":
        if order.status != "accepted":
            return "WRONG_STATE"
        if not order.packing_check_passed and not order.packing_override:
            return "PACKING_NOT_VERIFIED"
    if action == "mark_shipped":
        if order.status != "packed":
            return "NOT_PACKED"
        if not order.tracking_code:
            return "NO_TRACKING"
    if action == "cancel" and order.status not in ("new", "accepted"):
        return "WRONG_STATE"
    return None


def request_action(db: Session, seller: Seller, order: Order, action: str, reason: str | None = None) -> dict:
    h = seller.honorific
    err = can_order_action(db, order, action)
    if err:
        log_blocked(db, seller.id, 5, err, f"order:{order.id}:{action} status={order.status}")
        if err == "OUT_OF_STOCK":
            _, need, have, lst = stock_check(db, order)
            say = t("order_out_of_stock", h, need=f"{number_to_words(need)} {ls.container(lst)}",
                    have=number_to_words(have) if have else "không")
        elif err == "PACKING_NOT_VERIFIED":
            say = t("packing_not_verified", h)
        elif err == "NO_TRACKING":
            say = t("ship_need_tracking", h)
        elif err == "NOT_PACKED":
            say = t("ship_not_packed", h)
        else:
            say = f"Đơn này đang ở trạng thái: {ORDER_STATUS.get(order.status, order.status)}."
        return res(False, say=say, warnings=[{"code": err, "layer": 5, "params": {}}], data={"code": err})

    c = order_card(db, order)
    common = {"seller_id": seller.id, "subject_ref": f"order:{order.id}:{action}", "kind": "action", "risk": Risk.RED}
    its = items_spoken(db, order)
    if action == "accept":
        req = ConfirmationRequest(**common, prompt_text=t("order_accept_prompt", h, buyer=order.buyer_name, items=its,
                                                          payout=tp.money_spoken(order.seller_payout)),
                                  action_phrase="nhận đơn",
                                  card={**c, "kind": "confirm_order", "text": "Nhận đơn này?", "big": c["payout_big"], "risk": "red"})
    elif action == "mark_packed":
        req = ConfirmationRequest(**common, prompt_text=t("packed_prompt", h, buyer=order.buyer_name),
                                  action_phrase="đóng gói xong",
                                  card={**c, "kind": "confirm_order", "text": "Đã đóng gói xong?", "big": "📦", "risk": "red"})
    elif action == "packing_override":
        req = ConfirmationRequest(**{**common, "subject_ref": f"order:{order.id}:packing_override"},
                                  prompt_text=t("packing_override_prompt", h, buyer=order.buyer_name),
                                  card={**c, "kind": "confirm_order", "text": "Bỏ qua kiểm tra hàng?", "big": "⚠", "risk": "red"})
    elif action == "mark_shipped":
        req = ConfirmationRequest(**common, two_step=True, action_phrase="đã gửi rồi",
                                  prompt_text=t("ship_prompt", h, buyer=order.buyer_name, items=its, last4=_spell(order.tracking_code[-4:])),
                                  card={**c, "kind": "confirm_order", "text": "Đã gửi hàng?", "risk": "red", "two_step": True,
                                        "big": tp.tracking_grouped(order.tracking_code)})
    elif action == "cancel":
        if not reason:
            return res(False, say=t("cancel_ask_reason", h, options=", ".join(CANCEL_REASONS[:-1]) + " hay " + CANCEL_REASONS[-1]),
                       data={"need_reason": True, "options": CANCEL_REASONS})
        req = ConfirmationRequest(**common, two_step=True, action_phrase="hủy đơn",
                                  prompt_text=t("cancel_prompt", h, buyer=order.buyer_name, reason=reason),
                                  card={**c, "kind": "confirm_order", "text": f"Hủy đơn: {reason}", "big": "✖", "risk": "red", "two_step": True},
                                  payload={"reason": reason})
    else:
        return res(False, say="Tôi chưa làm được việc này.")
    return res(True, confirmation=req)


def _spell(s: str) -> str:
    return "-".join(tp.SPOKEN_CHAR.get(c, c) for c in s)


def apply_action(db: Session, seller: Seller, order: Order, action: str, payload: dict) -> str:
    h = seller.honorific
    if action == "accept":
        for it, lst in items(db, order):
            ls.apply_stock(db, lst, max(0, (lst.stock or 0) - it.quantity))
        order.status = "accepted"
        say = t("order_accepted", h)
    elif action == "mark_packed":
        order.status = "packed"
        say = t("packed_done", h)
    elif action == "packing_override":
        order.packing_override = True
        log_blocked(db, seller.id, 5, "PACKING_OVERRIDE", f"order:{order.id} người bán bỏ qua kiểm tra (đã xác nhận ĐỎ)")
        order.status = "packed"
        say = t("packed_done", h)
    elif action == "mark_shipped":
        order.status = "shipped"
        say = t("shipped_done", h, buyer=order.buyer_name)
    elif action == "cancel":
        if order.status == "accepted":
            for it, lst in items(db, order):
                ls.apply_stock(db, lst, (lst.stock or 0) + it.quantity)
        order.status = "cancelled"
        order.cancel_reason = payload.get("reason")
        say = t("cancelled_done", h, buyer=order.buyer_name)
    else:
        return ""
    order.updated_at = datetime.now()
    db.add(order)
    db.commit()
    return say


# ---------- kiểm tra đóng gói, biên nhận ----------

def packing_result(db: Session, seller: Seller, order: Order, image: Image, assessment: dict) -> dict:
    h = seller.honorific
    expected = expected_items(db, order)
    need_text = ", ".join(f"{number_to_words(e['count'])} {e['container']} {e['name'].lower()}"
                          + (f" {tp.volume_spoken(e['volume_ml'])}" if e.get("volume_ml") else "") for e in expected)
    if assessment["issue"]:
        return res(False, say=t(f"photo_guide_{assessment['issue']}", h), data={"status": "retake", "issue": assessment["issue"]})
    cmp = vision.compare_packing(expected, assessment["observations"])
    image.observations = {**(image.observations or {}), **assessment["observations"]}
    db.add(image)
    if cmp["status"] == "unsure":
        db.commit()
        return res(False, say=t("packing_unsure", h), data=cmp)
    if cmp["status"] == "fail":
        cont = expected[0]["container"]
        if cmp.get("reason") == "volume":
            seen = f"{cont} cỡ {tp.volume_spoken(int(cmp['vol_obs']))}"
            need = f"{cont} {tp.volume_spoken(int(cmp['vol_exp']))}"
        else:
            seen = f"{number_to_words(cmp['seen'])} {cont}" if cmp["seen"] else "không có hàng"
            need = f"{number_to_words(cmp['need'])} {cont}"
        log_blocked(db, seller.id, 3, "PACKING_MISMATCH", f"order:{order.id} cần {cmp['need']}, thấy {cmp['seen']}")
        order.packing_check_passed = False
        db.add(order)
        db.commit()
        return res(False, say=t("packing_mismatch", h, need=need, seen=seen), data=cmp,
                   warnings=[{"code": "PACKING_MISMATCH", "layer": 3, "params": cmp}])
    order.packing_check_passed = True
    db.add(order)
    db.commit()
    tip = ""
    for _, lst in items(db, order):
        fs = ls.fields(db, lst.id)
        if fs.get("container") and "nhựa" in (fs["container"].value or ""):
            tip = "Nhớ cho vào túi chống tràn."
        else:
            tip = catalog.category(lst.category).get("packing_tip", "")
    return res(True, say=t("packing_pass", h, need=need_text, tip=tip), data=cmp)


def set_tracking(db: Session, order: Order, code: str) -> None:
    order.tracking_code = code.replace(" ", "").upper()
    db.add(order)
    db.commit()


# ---------- gom đơn theo ngày gửi ----------

def next_shipping_dates(days: list[str], horizon_days: int = 7, today: date | None = None) -> list[date]:
    today = today or date.today()
    out = []
    for i in range(horizon_days + 1):
        d = today + timedelta(days=i)
        if WEEKDAY_KEYS[d.weekday()] in days:
            out.append(d)
    return out


def plan_shipping_trip(db: Session, seller: Seller, today: date | None = None) -> dict:
    h = seller.honorific
    today = today or date.today()
    pending = [o for o in open_orders(db, seller.id) if o.status in ("accepted", "packed", "new")]
    if not pending:
        return res(True, say=t("ship_plan_none", h), data={"plan": {}, "late": []})
    days = next_shipping_dates(seller.shipping_days or [], 7, today)
    plan: dict[date, list[Order]] = {d: [] for d in days}
    late: list[Order] = []
    for o in sorted(pending, key=lambda o: o.ship_by):
        day = next((d for d in days if d <= o.ship_by.date()), None)
        (plan[day] if day else late).append(o)
    parts = []
    for d, os_ in plan.items():
        if os_:
            label = "Hôm nay" if d == today else "Ngày mai" if d == today + timedelta(days=1) else DAY_NAMES[WEEKDAY_KEYS[d.weekday()]].capitalize()
            parts.append(t("ship_plan_day", h, day=label, n=number_to_words(len(os_))))
    late_text = ""
    if late:
        late_text = t("ship_plan_late", h, n=number_to_words(len(late)), deadline=tp.deadline_spoken(late[0].ship_by))
    return res(True, say=("".join(parts) + late_text).strip(),
               data={"plan": {d.isoformat(): [o.id for o in os_] for d, os_ in plan.items()}, "late": [o.id for o in late]})


def due_soon_unpacked(db: Session, seller_id: int) -> list[Order]:
    now = datetime.now()
    return [o for o in open_orders(db, seller_id) if o.status in ("new", "accepted") and 0 < tp.hours_left(o.ship_by, now) < 24]
