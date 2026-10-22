"""Định nghĩa + bộ điều phối công cụ cho LLM (mục 8). Mọi cổng chặn nằm trong services, không nằm ở LLM."""
from __future__ import annotations

from app import catalog
from app.agent.flow import Ctx, mode_request
from app.events import res
from app.models import BuyerMessage, GrowthSuggestion, Image, Listing, Order
from app.services import growth, orders as osv, policy, support, vision
from app.services import listings as ls


def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": required or []}}}


CATS = list(catalog.categories().keys())

SCHEMAS = [
    _fn("start_listing", "Bắt đầu phiếu sản phẩm mới theo ngành hàng. Trả về danh sách trường cần hỏi.",
        {"category": {"type": "string", "enum": CATS}}, ["category"]),
    _fn("set_field", "Ghi một giá trị vào phiếu (trạng thái HEARD). Validators tự chạy. Nếu trường RED/YELLOW, công cụ trả requires_confirmation.",
        {"listing_id": {"type": "integer"}, "key": {"type": "string"},
         "raw_text": {"type": "string", "description": "Nguyên văn đoạn người bán nói chứa giá trị"},
         "source": {"type": "string", "enum": ["voice", "image", "guardian"]}}, ["listing_id", "key", "raw_text", "source"]),
    _fn("next_missing_field", "Trả về trường bắt buộc tiếp theo chưa có và câu hỏi gợi ý.",
        {"listing_id": {"type": "integer"}}, ["listing_id"]),
    _fn("assess_photo", "Chấm chất lượng ảnh, sinh MỘT chỉ dẫn sửa cụ thể, và quan sát thuộc tính để đối chiếu.",
        {"image_id": {"type": "integer"}, "purpose": {"type": "string", "enum": ["listing", "packing_check", "receipt"]},
         "expect": {"type": "object"}}, ["image_id", "purpose"]),
    _fn("price_check", "Tra giá thị trường, tính phí và tiền thực nhận.", {"listing_id": {"type": "integer"}}, ["listing_id"]),
    _fn("policy_check", "Kiểm tra quy định ngành hàng và câu quảng cáo dễ vi phạm.", {"listing_id": {"type": "integer"}}, ["listing_id"]),
    _fn("draft_listing_text", "Lưu bản nháp tiêu đề và mô tả, CÓ thẻ [key]. Công cụ soát nguồn và trả lại bản đã làm sạch.",
        {"listing_id": {"type": "integer"}, "title": {"type": "string"}, "description_tagged": {"type": "string"}},
        ["listing_id", "title", "description_tagged"]),
    _fn("request_publish", "Yêu cầu đăng tin. Code kiểm tra đủ điều kiện; nếu đủ, trả requires_confirmation để xác nhận 2 bước.",
        {"listing_id": {"type": "integer"}}, ["listing_id"]),
    _fn("undo_last_action", "Hoàn tác hành động gần nhất còn trong thời gian cho phép (rút lại tin đang chờ)."),
    _fn("list_orders", "Tóm tắt đơn theo bộ lọc. Trả số liệu để agent nói ngắn gọn.",
        {"filter": {"type": "string", "enum": ["today", "new", "to_pack", "to_ship", "due_soon", "all_open"]}}, ["filter"]),
    _fn("get_order", "Lấy chi tiết một đơn theo mã, tên người mua hoặc 'latest'.",
        {"selector": {"type": "string"}}, ["selector"]),
    _fn("request_order_action", "Yêu cầu thao tác trên đơn. Luôn trả requires_confirmation. Code kiểm tra điều kiện.",
        {"order_id": {"type": "integer"}, "action": {"type": "string", "enum": ["accept", "cancel", "mark_packed", "mark_shipped"]},
         "reason": {"type": "string"}, "tracking_code": {"type": "string"}}, ["order_id", "action"]),
    _fn("packing_check", "So ảnh hàng chuẩn bị gửi với đơn (loại, số lượng).",
        {"order_id": {"type": "integer"}, "image_id": {"type": "integer"}}, ["order_id", "image_id"]),
    _fn("plan_shipping_trip", "Gom đơn theo ngày đi bưu cục của người bán và hạn từng đơn."),
    _fn("update_stock", "Cập nhật tồn kho (RED, cần xác nhận).",
        {"listing_id": {"type": "integer"}, "raw_text": {"type": "string"}}, ["listing_id", "raw_text"]),
    _fn("daily_briefing", "Tạo bản tin cuối ngày (số liệu + tối đa 1 gợi ý)."),
    _fn("get_growth_suggestion", "Lấy 1 gợi ý phát triển phù hợp nhất hiện tại, kèm bằng chứng số liệu."),
    _fn("respond_growth_suggestion", "Người bán đồng ý/từ chối gợi ý. Đồng ý -> requires_confirmation trước khi áp dụng.",
        {"suggestion_id": {"type": "integer"}, "decision": {"type": "string", "enum": ["accept", "decline", "later"]}},
        ["suggestion_id", "decision"]),
    _fn("answer_buyer", "Trả lời khách CHỈ từ trường CONFIRMED/FAQ đã duyệt. Phải liệt kê source_refs ('field:<listing_id>:<key>' | 'faq:<id>').",
        {"message_id": {"type": "integer"}, "answer": {"type": "string"}, "source_refs": {"type": "array", "items": {"type": "string"}}},
        ["message_id", "answer", "source_refs"]),
    _fn("ask_seller", "Chuyển câu hỏi của khách cho người bán; gửi khách câu chờ lịch sự.",
        {"message_id": {"type": "integer"}}, ["message_id"]),
    _fn("seller_answer", "Ghi câu trả lời của người bán, chuẩn hóa lịch sự, yêu cầu xác nhận trước khi gửi khách và lưu FAQ.",
        {"message_id": {"type": "integer"}, "raw_text": {"type": "string"}}, ["message_id", "raw_text"]),
    _fn("set_preferences", "Đổi chế độ, tốc độ đọc, ngày đi bưu cục. Đổi chế độ cần xác nhận.",
        {"mode": {"type": "string", "enum": ["voice", "touch"]}, "tts_speed": {"type": "number"},
         "shipping_days": {"type": "array", "items": {"type": "string"}}}),
]


def _own(ctx: Ctx, obj) -> bool:
    return obj is not None and getattr(obj, "seller_id", ctx.seller.id) == ctx.seller.id


async def dispatch(name: str, args: dict, ctx: Ctx) -> dict:
    db, seller, s = ctx.db, ctx.seller, ctx.s
    try:
        if name == "start_listing":
            lst = ls.start_listing(db, seller, args["category"])
            s.active_listing_id = lst.id
            return res(True, data={"listing_id": lst.id, "fields": [{"key": f["key"], "risk": f["risk"], "ask": f["ask"]}
                                                                    for f in catalog.category(lst.category)["fields"]]})
        if name in ("set_field", "next_missing_field", "price_check", "policy_check", "draft_listing_text", "request_publish", "update_stock"):
            lst = db.get(Listing, int(args["listing_id"]))
            if not _own(ctx, lst):
                return res(False, warnings=[{"code": "NOT_FOUND"}])
            s.active_listing_id = lst.id
            if name == "set_field":
                keys = [f["key"] for f in catalog.category(lst.category)["fields"]]
                if args["key"] not in keys:   # không cho mô hình tự đặt trường lạ (ví dụ "title")
                    return res(False, warnings=[{"code": "UNKNOWN_FIELD", "params": {"valid_keys": keys}}],
                               data={"valid_keys": {f["key"]: f["label"] for f in catalog.category(lst.category)["fields"]}})
                return ls.set_field(db, seller, lst, args["key"], args["raw_text"], args.get("source", "voice"), ctx.confidence)
            if name == "next_missing_field":
                tpl = ls.next_missing(db, lst)
                return res(True, data={"field": tpl, "unconfirmed": [f.key for f in ls.unconfirmed(db, lst)],
                                       "has_photo": ls.has_accepted_photo(db, lst)})
            if name == "price_check":
                return ls.price_report(db, seller, lst)
            if name == "policy_check":
                return res(True, data=policy.check(lst.category, lst.description or ""))
            if name == "draft_listing_text":
                return ls.save_draft(db, seller, lst, args["title"], args["description_tagged"])
            if name == "request_publish":
                return ls.request_publish(db, seller, lst)
            return ls.request_stock_update(db, seller, lst, args["raw_text"])
        if name == "assess_photo":
            img = db.get(Image, int(args["image_id"]))
            a = await vision.assess(img, args["purpose"])
            return res(True, data=a)
        if name == "undo_last_action":
            return ls.undo(db, seller)
        if name == "list_orders":
            return osv.list_orders(db, seller, args["filter"])
        if name == "get_order":
            o = osv.find(db, seller, args.get("selector"))
            if not o:
                return res(False, warnings=[{"code": "NOT_FOUND"}])
            s.active_order_id = o.id
            s.order_details_read = o.id
            return res(True, say=osv.order_detail(db, seller, o), data=osv.order_card(db, o))
        if name == "request_order_action":
            o = db.get(Order, int(args["order_id"]))
            if not _own(ctx, o):
                return res(False, warnings=[{"code": "NOT_FOUND"}])
            s.active_order_id = o.id
            if args.get("tracking_code"):
                osv.set_tracking(db, o, args["tracking_code"])
            return osv.request_action(db, seller, o, args["action"], args.get("reason"))
        if name == "packing_check":
            o = db.get(Order, int(args["order_id"]))
            img = db.get(Image, int(args["image_id"]))
            a = await vision.assess(img, "packing_check")
            return osv.packing_result(db, seller, o, img, a)
        if name == "plan_shipping_trip":
            return osv.plan_shipping_trip(db, seller)
        if name == "daily_briefing":
            r = growth.daily_briefing(db, seller)
            if r["data"].get("suggestion_id"):
                s.awaiting = ("growth", r["data"]["suggestion_id"])
            return r
        if name == "get_growth_suggestion":
            sug = growth.get_suggestion(db, seller)
            if sug:
                s.awaiting = ("growth", sug.id)
            return growth.suggestion_res(seller, sug)
        if name == "respond_growth_suggestion":
            sug = db.get(GrowthSuggestion, int(args["suggestion_id"]))
            if not _own(ctx, sug):
                return res(False, warnings=[{"code": "NOT_FOUND"}])
            return growth.respond(db, seller, sug, args["decision"])
        if name in ("answer_buyer", "ask_seller", "seller_answer"):
            msg = db.get(BuyerMessage, int(args["message_id"]))
            if not _own(ctx, msg):
                return res(False, warnings=[{"code": "NOT_FOUND"}])
            if name == "answer_buyer":
                return support.answer_buyer(db, msg, args["answer"], args.get("source_refs") or [])
            if name == "ask_seller":
                return support.ask_seller(db, seller, msg)
            s.active_message_id = msg.id
            return await support.seller_answer(db, seller, msg, args["raw_text"])
        if name == "set_preferences":
            if args.get("tts_speed"):
                seller.tts_speed = max(0.5, min(1.3, float(args["tts_speed"])))
            if args.get("shipping_days"):
                seller.shipping_days = args["shipping_days"]
            db.add(seller)
            db.commit()
            if args.get("mode") and args["mode"] != seller.mode.value:
                return res(True, confirmation=mode_request(ctx, args["mode"]))
            return res(True, data={"tts_speed": seller.tts_speed, "shipping_days": seller.shipping_days})
    except (KeyError, ValueError, TypeError) as e:
        return res(False, warnings=[{"code": "BAD_ARGS", "params": {"error": str(e)}}])
    return res(False, warnings=[{"code": "UNKNOWN_TOOL"}])


def for_llm(out: dict) -> dict:
    """Bản gửi lại cho LLM: không lộ đối tượng xác nhận, chỉ nói là đang chờ người bán."""
    d = {k: v for k, v in out.items() if k not in ("confirmation", "events")}
    if out.get("confirmation"):
        d["confirmation"] = {"status": "waiting_for_seller", "prompt": out["confirmation"].prompt_text}
    return d
