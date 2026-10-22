"""Bộ não hội thoại thời gian thực: gpt-realtime nói chuyện tự nhiên, làm việc qua công cụ của backend.

An toàn vẫn nằm trong code:
- Việc có hậu quả trả need_confirmation; mô hình phải đọc lại và chờ.
- Công cụ `confirm` KHÔNG tin lời mô hình: nó lấy bản ghi THẬT câu người bán vừa nói (trình duyệt gửi lên
  từ sự kiện nhận dạng giọng) rồi đưa vào Confirmation Engine.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime

from app import catalog
from app.agent import flow
from app.agent import tools as T
from app.agent.orchestrator import build_state_summary
from app.confirm import templates as tp
from app.confirm.engine import ConfirmationRequest, log_confirmation
from app.events import open_camera, speak
from app.i18n.vi import DAY_NAMES
from app.models import Risk, Seller
from app.services import listings as ls
from app.services import notifier, shopmaker

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
PROFILE_FIELDS = {   # khóa: (nhãn, bắt buộc)
    "name": ("tên người bán", True), "honorific": ("cách xưng hô", True), "shop_name": ("tên cửa hàng", True),
    "region": ("tỉnh", True), "address": ("địa chỉ lấy hàng", False), "phone": ("số điện thoại", False),
    "main_products": ("mặt hàng chính", True), "shipping_days": ("ngày đi gửi hàng", True), "intro": ("lời giới thiệu shop", False),
}
SKIP = {"answer_buyer", "ask_seller", "assess_photo", "packing_check", "draft_listing_text", "set_preferences"}
ACTION_TOOLS = {"start_listing", "sell_from_photo", "set_field", "request_publish", "request_order_action", "update_stock",
                "respond_growth_suggestion", "seller_answer", "undo_last_action", "complete_profile"}


def _fn(name, desc, props=None, required=None):
    return {"type": "function", "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}


def rt_tools() -> list[dict]:
    base = [_fn(s["function"]["name"], s["function"]["description"], s["function"]["parameters"].get("properties"),
                s["function"]["parameters"].get("required")) for s in T.SCHEMAS if s["function"]["name"] not in SKIP]
    return base + [
        _fn("update_profile", "Lưu thông tin hồ sơ cửa hàng ngay khi nghe được (có thể nhiều trường một lúc). Trả lại các trường còn thiếu.",
            {"name": {"type": "string", "description": "Họ tên người bán"},
             "honorific": {"type": "string", "enum": ["cô", "chú", "bác", "chị", "anh", "em", "bà", "ông"]},
             "shop_name": {"type": "string"}, "region": {"type": "string", "description": "Tỉnh"},
             "address": {"type": "string", "description": "Xã/huyện, nơi lấy hàng"},
             "phone": {"type": "string", "description": "Chỉ chữ số"},
             "main_products": {"type": "string", "description": "Ví dụ: mật ong, chè"},
             "shipping_days": {"type": "array", "items": {"type": "string", "enum": WEEKDAYS}},
             "intro": {"type": "string", "description": "1-2 câu giới thiệu shop, CHỈ từ lời người bán"}}),
        _fn("complete_profile", "Khi đủ thông tin bắt buộc: đọc lại hồ sơ để người bán xác nhận."),
        _fn("confirm", "Gọi NGAY sau khi người bán trả lời một câu xác nhận (đúng/sai/sửa lại). Hệ thống tự dùng nguyên văn lời người bán; không cần tham số."),
        _fn("open_camera", "Mở camera để người bán chụp (ảnh sản phẩm, hàng đóng gói, biên nhận). Người bán nói 'chụp' để chụp.",
            {"purpose": {"type": "string", "enum": ["listing", "packing_check", "receipt"]}}, ["purpose"]),
        _fn("sell_from_photo", "CÁCH NHANH NHẤT để đăng sản phẩm mới: mở camera; người bán chụp một ảnh và nói vài câu về hàng "
            "(tên, giá hoặc giá thấp nhất, số lượng). AI tự điền tin đăng, đề xuất giá, làm ảnh quảng cáo."),
        _fn("remove_listing_photo", "Bỏ một ảnh quảng cáo của sản phẩm đang làm theo ý người bán.",
            {"kind": {"type": "string", "enum": ["scene", "text", "main"], "description": "scene=ảnh bối cảnh, text=ảnh có chữ, main=ảnh nền trắng"}}, ["kind"]),
        _fn("set_shop_color", "Đổi màu chủ đạo của gian hàng theo lời người bán (ví dụ 'xanh lá' -> mã màu).",
            {"color_hex": {"type": "string", "description": "#rrggbb"}}, ["color_hex"]),
        _fn("next_task", "Tìm việc quan trọng nhất đang chờ (đơn mới, đơn cần đóng gói, khách hỏi, tin đăng dở)."),
        _fn("shop_status", "Xem nhanh tình hình cửa hàng: hồ sơ, sản phẩm, đơn đang mở, khách chờ."),
    ]


def address_words(seller: Seller) -> tuple[str, str]:
    """(gọi người bán, tự xưng)."""
    h = seller.honorific or ""
    if h in ("cô", "chú", "bác", "bà", "ông"):
        return h, "cháu"
    if h in ("anh", "chị"):
        return h, "em"
    return h or "bạn", "mình"


def profile_view(seller: Seller) -> tuple[dict, list[str]]:
    vals = {"name": seller.name, "honorific": seller.honorific if seller.name else "", "shop_name": seller.shop_name,
            "region": seller.region, "address": seller.address, "phone": seller.phone, "main_products": seller.main_products,
            "shipping_days": ", ".join(DAY_NAMES[d] for d in seller.shipping_days or []), "intro": seller.intro}
    missing = [k for k, (_, req) in PROFILE_FIELDS.items() if req and not vals.get(k)]
    return vals, missing


def profile_event(seller: Seller, saved: list[str] | None = None) -> dict:
    vals, missing = profile_view(seller)
    return {"type": "profile", "onboarded": seller.onboarded, "saved": saved or [], "missing": len(missing),
            "fields": [{"key": k, "label": label, "required": req, "value": vals.get(k) or None}
                       for k, (label, req) in PROFILE_FIELDS.items()]}


def instructions(db, seller: Seller, s) -> str:
    you, me = address_words(seller)
    vals, missing = profile_view(seller)
    prof = "; ".join(f"{PROFILE_FIELDS[k][0]}: {v}" for k, v in vals.items() if v) or "chưa có gì"
    if not seller.onboarded:
        goal = (f"HỒ SƠ CHƯA XONG. Còn thiếu: {', '.join(PROFILE_FIELDS[k][0] for k in missing) or 'không, gọi complete_profile'}. "
                "Dẫn dắt như người hướng dẫn mở shop ngồi cạnh họ: mở đầu bằng một câu nói ngắn là mình sẽ cùng lập "
                "cửa hàng, chỉ mất vài phút. Hỏi lần lượt (mỗi lượt một câu), gọi update_profile ngay khi nghe được. "
                "Khi hỏi, nói kèm lý do ngắn để họ hiểu (ví dụ: 'để khách biết hàng gửi từ đâu'). "
                "Họ kể chuyện ngoài lề (gia đình, vụ mùa, cách làm hàng) thì đáp lại một câu thật lòng, "
                "và nếu có ý hay cho lời giới thiệu shop thì lưu vào intro bằng chính lời họ. "
                "Có thể hỏi thêm địa chỉ lấy hàng, số điện thoại, nhưng họ không muốn thì bỏ qua. "
                "Đủ thông tin bắt buộc thì gọi complete_profile.")
    else:
        goal = ("Hồ sơ đã xong. Giúp người bán theo thứ tự: xử lý đơn đang chờ (next_task); nếu chưa có sản phẩm đang bán "
                "thì gợi ý đăng sản phẩm đầu tiên; sau đó gợi ý tăng đơn (get_growth_suggestion) hoặc bản tin (daily_briefing).")
    cats = ", ".join(f"{k} ({v['label']})" for k, v in catalog.categories().items())
    return f"""Bạn là "Bạn Bán Hàng", trợ lý bán hàng trên sàn thương mại điện tử, đang nói chuyện qua điện thoại với người bán.
Người bán có thể là người lớn tuổi, người vùng cao, hoặc khiếm thị: họ chỉ nghe và nói, KHÔNG nhìn màn hình.
Xưng hô hiện tại: gọi người bán là "{you}", tự xưng là "{me}". Khi biết cách xưng hô mới, đổi theo ngay:
cô/chú/bác/bà/ông -> tự xưng "cháu"; anh/chị -> tự xưng "em"; em -> tự xưng "anh" hoặc "chị" tùy giọng, mặc định "mình".

CÁCH NÓI (như một người hướng dẫn thật, không như máy đọc)
- Tiếng Việt giọng Hà Nội, phát âm rõ. Giọng ấm, có lên xuống tự nhiên như đang trò chuyện, cười nhẹ trong giọng
  khi chào hỏi hoặc khen; chậm lại và rõ hơn khi đọc số, tên, ngày.
- Dùng tiếng đệm của người thật khi đáp: "Dạ", "Vâng ạ", "À", "Ồ hay quá", "Thế thì tốt ạ". Phản hồi đúng điều họ
  vừa nói (ví dụ họ nói bán mật ong ở Hà Giang: "Ồ, mật ong Hà Giang thì thơm lắm ạ.") rồi mới hỏi tiếp.
- Mỗi lượt 1-2 câu ngắn, chỉ hỏi MỘT câu. Không đọc danh sách dài, không gạch đầu dòng, không từ chuyên môn.
- Không lặp một kiểu câu mở đầu liên tục; đổi cách nói cho tự nhiên.
- KHÔNG nói câu kiểu "để mình lưu lại", "mình đang cập nhật". Gọi công cụ lặng lẽ, màn hình tự hiện thông tin.
- Người bán nói chen thì dừng lại nghe. Không chắc nghe đúng thì hỏi lại ngắn gọn, nhắc lại đúng chữ mình nghe được.
- Người bán nói nhiều thông tin một lúc thì lưu hết một lần, không hỏi lại điều họ đã nói.
- Họ ngập ngừng hoặc im lặng lâu thì gợi ý nhẹ một ví dụ câu trả lời.

TRUNG THỰC
- GỌI CÔNG CỤ TRƯỚC, NÓI SAU. Chỉ nhắc lại thông tin đúng như kết quả công cụ trả về; tuyệt đối không tự đoán tên, số, địa chỉ.

MỤC TIÊU
{goal}

QUY TẮC BẮT BUỘC
1. Công cụ trả need_confirmation=true: đọc NGUYÊN VĂN câu trong "say" (không đổi số, không rút gọn), rồi chờ người bán trả lời.
   Ngay khi họ trả lời, gọi confirm. Tuyệt đối không tự cho là họ đồng ý, không tự trả lời thay.
2. Chỉ nói "đã đăng", "đã nhận đơn", "đã gửi", "đã lưu" khi công cụ trả về như vậy.
3a. Người bán muốn bán món mới: ưu tiên sell_from_photo. Nói họ hướng máy vào món hàng, nói "chụp",
   và kể luôn tên hàng, giá (hoặc giá thấp nhất chịu bán), số lượng. Sau đó máy chủ sẽ báo kết quả để mình đọc lại.
   Họ muốn bỏ ảnh nào thì remove_listing_photo; muốn đổi màu gian hàng thì set_shop_color.
3. Đăng sản phẩm không có ảnh: start_listing (ngành: {cats}); kết quả có field_keys (name=tên, price=giá, volume_ml=dung tích,
   stock=số lượng...). Với mỗi thông tin người bán nói, gọi set_field đúng khóa trong field_keys, raw_text là NGUYÊN VĂN
   câu người bán (một câu có cả tên và giá thì gọi set_field hai lần: name rồi price). Hỏi tiếp theo đúng câu "say"
   của kết quả công cụ. Cần ảnh thì gọi open_camera và bảo họ nói "chụp".
4. Không bịa thông tin sản phẩm, không hứa điều người bán không nói. Số tiền, số lượng để công cụ đọc lại.
5. Có "say" trong kết quả công cụ thì nói lại đúng nội dung đó (có thể thêm một từ đệm tự nhiên), giữ nguyên các con số.
6. Tin nhắn hệ thống "Thông báo từ máy chủ" (đơn mới, khách hỏi, kết quả ảnh): báo lại NỘI DUNG cho người bán,
   không đọc chữ "thông báo từ máy chủ", không đọc dấu ngoặc.

TRẠNG THÁI HIỆN TẠI
Hồ sơ: {prof}
{build_state_summary(flow.Ctx(db=db, seller=seller, s=s))}

Khi cuộc gọi bắt đầu: chào ngắn gọn, ấm áp, rồi đi ngay vào việc quan trọng nhất."""


# ---------------- lời thật của người bán ----------------

def record_heard(s, text: str) -> None:
    s.heard.append((datetime.now(), text))
    del s.heard[:-20]
    s.heard_event.set()


async def wait_heard(s, after: datetime, timeout: float = 4.0) -> str | None:
    """Câu người bán nói sau thời điểm `after` (chờ bản ghi nhận dạng tới, tối đa vài giây)."""
    end = asyncio.get_event_loop().time() + timeout
    while True:
        fresh = [t for ts, t in s.heard if ts > after]
        if fresh:
            return fresh[-1]
        left = end - asyncio.get_event_loop().time()
        if left <= 0:
            return None
        s.heard_event.clear()
        try:
            await asyncio.wait_for(s.heard_event.wait(), left)
        except asyncio.TimeoutError:
            return None


# ---------------- chạy công cụ ----------------

async def _pack(seller: Seller, s, events: list[dict], extra: dict | None = None) -> dict:
    said = " ".join(e["text"] for e in events if e.get("type") == "speak")
    for e in events:
        if e.get("type") == "speak":
            notifier.subtitle(seller.id, "agent", e["text"])
    others = [e for e in events if e.get("type") != "speak"]
    if others:   # thẻ, camera... vẫn hiện trên điện thoại / bảng demo
        await notifier.push(seller.id, others)
    # nhiều công cụ trong cùng một lượt có thể trả cùng một câu hỏi tiếp theo -> chỉ nói một lần
    now = datetime.now()
    if said and said == getattr(s, "rt_last_say", "") and (now - getattr(s, "rt_last_at", now)).total_seconds() < 8:
        said = ""
        extra = {**(extra or {}), "note": "Câu tiếp theo đã được nói ở kết quả trước, không nói lại."}
    elif said:
        s.rt_last_say, s.rt_last_at = said, now
    out = {"ok": True, "say": said, **(extra or {})}
    if s.pending:
        out["need_confirmation"] = True
    return out


def _clean_phone(v: str) -> str | None:
    d = re.sub(r"\D", "", v or "")
    return d if re.fullmatch(r"0\d{8,10}", d) else None


async def run(db, seller: Seller, s, name: str, args: dict) -> dict:
    ctx = flow.Ctx(db=db, seller=seller, s=s)

    if name == "confirm":
        if not s.pending:
            return {"ok": False, "note": "Không có gì đang chờ xác nhận."}
        text = await wait_heard(s, after=s.pending.asked_at)
        if not text:
            return {"ok": False, "note": "Chưa nghe rõ người bán trả lời. Hỏi lại họ: đúng hay sai?"}
        ctx.text = text
        return await _pack(seller, s, await flow.handle_pending(ctx), {"heard": text})

    if s.pending and name in ACTION_TOOLS:   # người bán chuyển sang việc khác: không bao giờ coi là đồng ý
        log_confirmation(db, s.pending, "unclear", f"(chuyển sang {name})", None)
        s.pending = None

    if name == "update_profile":
        saved, problems = {}, []
        for k, v in args.items():
            if k not in PROFILE_FIELDS or v in (None, "", []):
                continue
            if k == "phone":
                v = _clean_phone(str(v))
                if not v:
                    problems.append("số điện thoại chưa đúng (cần bắt đầu bằng 0, 9-11 chữ số)")
                    continue
            if k == "shipping_days":
                v = [d for d in v if d in WEEKDAYS]
                if not v:
                    continue
            if k == "region":
                setattr(seller, "region", str(v).strip())
            else:
                setattr(seller, k, v.strip() if isinstance(v, str) else v)
            saved[k] = v
        db.add(seller)
        db.commit()
        await notifier.push(seller.id, [profile_event(seller, list(saved))])   # màn hình điền ngay khi nghe được
        _, missing = profile_view(seller)
        you, me = address_words(seller)
        return {"ok": True, "saved": saved, "problems": problems, "xung_ho": f"gọi '{you}', tự xưng '{me}'",
                "missing": [PROFILE_FIELDS[k][0] for k in missing],
                "next": "Hỏi trường tiếp theo trong missing" if missing else "Gọi complete_profile"}

    if name == "complete_profile":
        vals, missing = profile_view(seller)
        if missing:
            return {"ok": False, "missing": [PROFILE_FIELDS[k][0] for k in missing]}
        you, me = address_words(seller)
        where = seller.address or seller.region
        if seller.region and seller.region.lower() not in where.lower():
            where += f", {seller.region}"
        days = [DAY_NAMES[d] for d in seller.shipping_days or []]
        days_text = ", ".join(days[:-1]) + f" và {days[-1]}" if len(days) > 1 else "".join(days)
        parts = [f"{me.capitalize()} đọc lại hồ sơ của {you} nhé",
                 f"{you.capitalize()} {seller.name}, cửa hàng {seller.shop_name}, ở {where}",
                 f"Bán {seller.main_products}", f"Đi gửi hàng {days_text}"]
        if seller.phone:
            parts.append("Số điện thoại " + " ".join(tp.SPOKEN_CHAR.get(c, c) for c in seller.phone))
        req = ConfirmationRequest(seller_id=seller.id, subject_ref=f"seller:{seller.id}:profile", kind="action",
                                  risk=Risk.YELLOW, prompt_text=". ".join(parts) + ". Đúng không ạ?",
                                  card={"kind": "confirm", "big": seller.shop_name, "text": "Hồ sơ cửa hàng"})
        return await _pack(seller, s, flow.ask_confirmation(ctx, req))

    if name == "open_camera":
        purpose = args.get("purpose", "listing")
        ref = s.active_listing_id if purpose == "listing" else s.active_order_id
        s.awaiting = ("photo", purpose, ref)
        guide = {"listing": "Đặt sản phẩm giữa khung, chỗ sáng", "packing_check": "Bày đủ hàng của đơn lên bàn",
                 "receipt": "Chụp tờ biên nhận"}.get(purpose, "Chụp ảnh")
        await notifier.push(seller.id, [open_camera(purpose, guide, ref)])
        return {"ok": True, "note": "Camera đã mở. Bảo người bán hướng điện thoại vào hàng rồi nói 'chụp'."}

    if name == "sell_from_photo":
        s.quick_since = datetime.now()
        await notifier.push(seller.id, [open_camera("listing", "Hướng máy vào món hàng, chỗ sáng")])
        return {"ok": True, "note": "Camera đã mở. Bảo người bán hướng máy vào món hàng rồi nói 'chụp', "
                                    "và kể luôn tên hàng, giá, số lượng. Chờ máy chủ báo kết quả, không tự đoán."}

    if name == "remove_listing_photo":
        lst = db.get(ls.Listing, s.active_listing_id) if s.active_listing_id else None
        if not lst or not shopmaker.remove_image(db, lst, args.get("kind", "")):
            return {"ok": False, "note": "Không có ảnh đó để bỏ."}
        await notifier.push(seller.id, [flow.listing_event(db, lst)])
        return {"ok": True, "say": "Dạ, đã bỏ ảnh đó."}

    if name == "set_shop_color":
        color = shopmaker.theme_color(args.get("color_hex"))
        seller.theme = {**(seller.theme or {}), "color": color}
        db.add(seller)
        db.commit()
        return {"ok": True, "color": color, "note": "Đã đổi màu gian hàng (đã chỉnh đậm cho chữ dễ đọc)."}

    if name == "next_task":
        return await _pack(seller, s, await flow.next_task(ctx))

    if name == "shop_status":
        vals, missing = profile_view(seller)
        return {"ok": True, "profile_missing": [PROFILE_FIELDS[k][0] for k in missing],
                "status": build_state_summary(ctx)}

    out = await T.dispatch(name, args, ctx)
    data = T.for_llm(out)
    # "nhận đơn" ngay sau khi đã nghe đọc đủ chi tiết đơn (mục 11.2): chấp nhận luôn, theo lời THẬT của người bán
    req = out.get("confirmation")
    if req and name == "request_order_action" and args.get("action") == "accept":
        oid = int(req.subject_ref.split(":")[1])
        recent = [t for ts, t in s.heard if (datetime.now() - ts).total_seconds() < 20]
        if s.order_details_read == oid and recent and "nhận đơn" in recent[-1].lower() and " không" not in f" {recent[-1].lower()}":
            log_confirmation(db, req, "confirmed", recent[-1], None)
            s.order_details_read = None
            s.pending = None
            return await _pack(seller, s, await flow.apply_confirmed(ctx, req))
    if name in ("start_listing", "set_field") and out["ok"] and not out["requires_confirmation"]:
        lst = db.get(ls.Listing, s.active_listing_id) if s.active_listing_id else None
        if lst:   # code quyết định bước tiếp theo của phiếu (hỏi trường còn thiếu / ảnh / đọc lại để đăng)
            fields = {f["key"]: f["label"] for f in catalog.category(lst.category)["fields"]}
            return await _pack(seller, s, await flow.continue_listing(ctx, lst),
                               {"listing_id": lst.id, "field_keys": fields,
                                "hint": "Người bán đã nói tên/giá thì gọi set_field cho từng khóa (name, price...) với raw_text là nguyên câu."})
    if out["requires_confirmation"]:
        req = out["confirmation"]
        if req.kind == "field":   # đọc lại theo đúng thứ tự trường (tên trước, giá sau...)
            lst = db.get(ls.Listing, int(req.subject_ref.split(":")[1]))
            events = await flow.continue_listing(ctx, lst)
        else:
            events = flow.ask_confirmation(ctx, req)
        return await _pack(seller, s, events, {"data": data.get("data", {})})
    if out.get("events") or out.get("say"):
        events = list(out.get("events") or [])
        if out.get("say"):
            events.insert(0, speak(out["say"]))
        return await _pack(seller, s, events, {"ok": out["ok"], "data": data.get("data", {}), "warnings": data.get("warnings", [])})
    return data
