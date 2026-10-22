"""FastAPI app: REST + WebSocket + Shopee giả lập. Chạy: uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic import Field as PField
from sqlmodel import func, select

from app import catalog, config
from app.agent import flow, orchestrator, session as sessions
from app.config import UPLOAD_DIR
from app.db import get_session, init_db, reset
from app.demo_photos import PHOTO_DIR
from app.events import speak
from app.i18n.vi import t
from app.mock_shopee import simulator
from app.mock_shopee.router import public_listing, router as shopee_router
from datetime import datetime, timedelta

from app.models import (BlockedError, BuyerMessage, ConfirmationLog, GuardianApproval, Image, Listing, Mode, Order,
                        Seller)
from app.services import listings as ls
from app.services import notifier, orders as osv, support

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bkrc")
_warned_due: set[int] = set()


async def background_loop():
    """Tin chờ hết hạn rút lại -> đăng; đơn còn < 24 giờ chưa đóng gói -> cảnh báo (mỗi đơn một lần)."""
    while True:
        await asyncio.sleep(2)
        try:
            await tick()
        except Exception as e:
            log.warning("background tick: %s", e)


async def tick(force_publish: bool = False):
    pushes: list[tuple[int, list[dict]]] = []
    with get_session() as db:
        for lst in ls.finalize_due(db, force=force_publish):
            seller = db.get(Seller, lst.seller_id)
            pushes.append((seller.id, [speak(t("publish_done", seller.honorific, name=ls.name_of(db, lst))),
                                       {"type": "notify", "kind": "published", "payload": {"listing_id": lst.id}, "vibrate": [100]}]))
        for seller in db.exec(select(Seller)).all():
            for o in osv.due_soon_unpacked(db, seller.id):
                if o.id not in _warned_due:
                    _warned_due.add(o.id)
                    pushes.append((seller.id, [{"type": "notify", "kind": "warning", "vibrate": [400, 100, 400],
                                                "payload": {"order_id": o.id, "text": t("warn_due_soon", seller.honorific, buyer=o.buyer_name)}}]))
    for sid, ev in pushes:
        await notifier.push(sid, ev)
        await push_board(sid)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    UPLOAD_DIR.mkdir(exist_ok=True)
    init_db()
    with get_session() as db:
        if not db.exec(select(Seller)).first():
            reset()
    task = asyncio.create_task(background_loop())
    yield
    task.cancel()


app = FastAPI(title="Bán Không Rào Cản", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(shopee_router)


# ---------------- board ----------------

LAYER_NAMES = {1: "Nghe nhầm", 2: "Bất hợp lý", 3: "Đối chiếu ảnh/nguồn", 4: "Gật đầu theo quán tính", 5: "Cổng chặn"}


def board_snapshot(seller_id: int) -> dict:
    s = sessions.get(seller_id)
    with get_session() as db:
        seller = db.get(Seller, seller_id)
        lst = db.get(Listing, s.active_listing_id) if s.active_listing_id else None
        lst = lst or db.exec(select(Listing).where(Listing.seller_id == seller_id).order_by(Listing.id.desc())).first()
        listing = None
        if lst:
            listing = {"id": lst.id, "status": lst.status, "title": lst.title, "category": lst.category,
                       "description": lst.public_description, "pending_until": lst.pending_until.isoformat() if lst.pending_until else None,
                       "images": [f"/api/images/{i}/file" for i in (lst.image_ids or [])],
                       "fields": [{"key": f.key, "label": ls.label_of(lst, f.key), "value": ls.short_value(lst, f.key, f.value) if f.value else None,
                                   "risk": f.risk.value, "state": f.state.value, "source": f.source.value if f.source else None}
                                  for f in ls.fields(db, lst.id).values()]}
        counts = dict(db.exec(select(BlockedError.layer, func.count()).where(BlockedError.seller_id == seller_id)
                              .group_by(BlockedError.layer)).all())
        recent = db.exec(select(BlockedError).where(BlockedError.seller_id == seller_id).order_by(BlockedError.id.desc()).limit(12)).all()
        orders = db.exec(select(Order).where(Order.seller_id == seller_id).order_by(Order.id.desc()).limit(8)).all()
        confirms = db.exec(select(func.count()).select_from(ConfirmationLog).where(ConfirmationLog.seller_id == seller_id)).one()
        guardian = db.exec(select(GuardianApproval).where(GuardianApproval.seller_id == seller_id, GuardianApproval.status == "waiting")).all()
        return {
            "seller": {"id": seller.id, "name": seller.name, "mode": seller.mode.value, "tts_speed": seller.tts_speed,
                       "guardian_required": seller.guardian_required, "guardian_name": seller.guardian_name},
            "agent_mode": config.AGENT_MODE,
            "subtitles": notifier.subtitles(seller_id),
            "listing": listing,
            "blocked": {"by_layer": [{"layer": k, "name": v, "count": counts.get(k, 0)} for k, v in LAYER_NAMES.items()],
                        "total": sum(counts.values()), "confirmations": confirms,
                        "recent": [{"layer": b.layer, "code": b.code, "detail": b.detail, "at": b.created_at.isoformat(timespec="seconds")} for b in recent]},
            "orders": [osv.order_card(db, o) for o in orders],
            "pending": {"subject_ref": s.pending.subject_ref, "prompt": s.pending.prompt_text, "risk": s.pending.risk.value,
                        "two_step": s.pending.two_step, "flags": s.pending.flags} if s.pending else None,
            "awaiting": list(s.awaiting) if s.awaiting else None,
            "guardian": [{"id": g.id, "subject_ref": g.subject_ref, "summary": g.summary} for g in guardian],
            "shop": [public_listing(db, l) for l in db.exec(select(Listing).where(Listing.seller_id == seller_id,
                                                                                   Listing.status == "published")).all()],
            "waiting_questions": len(support.waiting(db, seller_id)),
            "script": simulator.script(),
        }


async def push_board(seller_id: int):
    if notifier.has_board(seller_id):
        await notifier.push_board(seller_id, board_snapshot(seller_id))


async def run_and_push(seller_id: int, inp: dict) -> list[dict]:
    events = await orchestrator.handle_turn(seller_id, inp)
    await notifier.push(seller_id, events)
    await push_board(seller_id)
    return events


# ---------------- WebSocket ----------------

@app.websocket("/ws/session/{seller_id}")
async def ws_session(ws: WebSocket, seller_id: int):
    await ws.accept()
    notifier.connect(seller_id, ws)
    with get_session() as db:
        seller = db.get(Seller, seller_id)
        await ws.send_json({"type": "hello", "seller": {"id": seller.id, "name": seller.name, "mode": seller.mode.value,
                                                        "honorific": seller.honorific, "tts_speed": seller.tts_speed,
                                                        "onboarded": seller.onboarded},
                            "agent_mode": config.AGENT_MODE, "stt": config.STT_PROVIDER, "tts": config.TTS_PROVIDER})
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                continue
            await run_and_push(seller_id, msg)
    except WebSocketDisconnect:
        notifier.disconnect(seller_id, ws)


@app.websocket("/ws/board/{seller_id}")
async def ws_board(ws: WebSocket, seller_id: int):
    await ws.accept()
    notifier.connect(seller_id, ws, board=True)
    await ws.send_json({"type": "board_update", "payload": board_snapshot(seller_id)})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        notifier.disconnect(seller_id, ws)


# ---------------- REST ----------------

class SellerIn(BaseModel):
    name: str = PField(min_length=2, max_length=60)
    honorific: str = PField("cô", max_length=10)
    shop_name: str | None = PField(None, max_length=80)
    region: str | None = PField(None, max_length=60)
    mode: Mode = Mode.VOICE
    shipping_days: list[str] = []
    guardian_required: bool = False
    guardian_name: str | None = PField(None, max_length=60)
    avatar: str = PField("🏪", max_length=8)


@app.post("/api/sellers")
def create_seller(body: SellerIn):
    """Tạo hồ sơ người bán mới (bước đầu tiên của trợ lý)."""
    days = [d for d in body.shipping_days if d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]
    with get_session() as db:
        s = Seller(**{**body.model_dump(), "shipping_days": days or ["tue", "fri"]},
                   uses_assistant=True, shop_name=body.shop_name or f"Shop {body.name}")
        db.add(s)
        db.commit()
        return s


@app.get("/api/sellers")
def list_sellers():
    with get_session() as db:
        return [{"id": s.id, "name": s.name, "shop_name": s.shop_name, "region": s.region, "avatar": s.avatar,
                 "mode": s.mode.value} for s in db.exec(select(Seller).where(Seller.uses_assistant == True, Seller.onboarded == True)).all()]  # noqa: E712


class TTSIn(BaseModel):
    text: str = PField(min_length=1, max_length=600)
    speed: float = 0.9


@app.post("/api/speech/tts")
async def speech_tts(body: TTSIn):
    """Đọc một câu (dùng cho màn tạo hồ sơ, trước khi có phiên trợ lý)."""
    from app.speech import tts
    if not tts.enabled():
        return {"audio": None}
    import base64
    return {"audio": base64.b64encode(await tts.synthesize(body.text, body.speed)).decode()}


@app.post("/api/sellers/draft")
def create_draft_seller():
    """Mở app lần đầu: tạo hồ sơ nháp, trợ lý sẽ trò chuyện để điền."""
    with get_session() as db:
        s = Seller(name="", honorific="", shop_name=None, onboarded=False, uses_assistant=True, shipping_days=[], avatar="🏪")
        db.add(s)
        db.commit()
        return {"id": s.id}


@app.post("/api/rt/session/{seller_id}")
async def realtime_session(seller_id: int, agent: bool = False):
    """Khóa tạm (vài phút) để trình duyệt nối thẳng WebRTC tới Realtime. Khóa thật không rời server.
    agent=true: mô hình trò chuyện tự nhiên và làm việc qua công cụ (rt_tools)."""
    from app.agent import realtime, rt_tools
    if not config.OPENAI_API_KEY:
        raise HTTPException(503, "Chưa có key cho hội thoại thời gian thực")
    speed, instructions, tools = 0.88, None, None
    if seller_id:
        with get_session() as db:
            seller = db.get(Seller, seller_id)
            if not seller:
                raise HTTPException(404)
            speed = seller.tts_speed
            if agent:
                instructions = rt_tools.instructions(db, seller, sessions.get(seller_id))
                tools = rt_tools.rt_tools()
    try:
        return await realtime.create_session(speed, instructions, tools)
    except Exception as e:
        log.warning("realtime session failed: %s", e)
        raise HTTPException(502, "Không tạo được phiên thoại")


class HeardIn(BaseModel):
    text: str = PField(min_length=1, max_length=1000)


@app.post("/api/rt/heard/{seller_id}")
async def realtime_heard(seller_id: int, body: HeardIn):
    """Bản ghi THẬT lời người bán (từ nhận dạng giọng). Công cụ confirm chỉ tin nguồn này."""
    from app.agent import rt_tools
    rt_tools.record_heard(sessions.get(seller_id), body.text.strip())
    notifier.subtitle(seller_id, "seller", body.text.strip())
    await push_board(seller_id)
    return {"ok": True}


class ToolIn(BaseModel):
    name: str = PField(max_length=60)
    args: dict = {}


@app.post("/api/rt/tool/{seller_id}")
async def realtime_tool(seller_id: int, body: ToolIn):
    from app.agent import rt_tools
    with get_session() as db:
        seller = db.get(Seller, seller_id)
        if not seller:
            raise HTTPException(404)
        try:
            out = await rt_tools.run(db, seller, sessions.get(seller_id), body.name, body.args or {})
        except Exception as e:
            log.exception("rt tool %s failed", body.name)
            out = {"ok": False, "error": f"Lỗi hệ thống: {type(e).__name__}. Xin lỗi người bán và thử cách khác."}
    log.info("rt tool %s(%s) -> %s", body.name, body.args, str(out)[:200])
    await push_board(seller_id)
    return out


@app.post("/api/speech/stt")
async def speech_stt(audio: UploadFile = File(...), hint: str | None = Form(None)):
    from app.speech import stt
    if not stt.enabled():
        raise HTTPException(503, "Chưa bật nhận dạng giọng nói phía server")
    data = await audio.read()
    if len(data) > 8_000_000:
        raise HTTPException(413, "Âm thanh quá dài")
    prompt = stt.PROMPT + (f" Ngữ cảnh: {hint[:200]}" if hint else "")
    tr = await stt.transcribe(data, audio.filename or "speech.webm", prompt=prompt)
    return {"text": tr.text, "confidence": tr.confidence}


@app.get("/api/sellers/{seller_id}")
def get_seller(seller_id: int):
    with get_session() as db:
        s = db.get(Seller, seller_id)
        if not s:
            raise HTTPException(404)
        return s


class PrefsIn(BaseModel):
    mode: Mode | None = None
    tts_speed: float | None = None
    shipping_days: list[str] | None = None
    guardian_required: bool | None = None
    mode_now: Mode | None = None   # chạm "Dùng bằng chữ": người khiếm thính không nghe được câu hỏi xác nhận


@app.patch("/api/sellers/{seller_id}/preferences")
async def patch_prefs(seller_id: int, body: PrefsIn):
    """Tốc độ, ngày gửi, bảo trợ đổi ngay; đổi chế độ phải qua xác nhận của người bán."""
    events = []
    with get_session() as db:
        s = db.get(Seller, seller_id)
        if body.tts_speed:
            s.tts_speed = max(0.5, min(1.3, body.tts_speed))
        if body.shipping_days is not None:
            s.shipping_days = body.shipping_days
        if body.guardian_required is not None:
            s.guardian_required = body.guardian_required
        if body.mode_now:
            s.mode = body.mode_now
            events = [{"type": "mode", "mode": body.mode_now.value}]
        db.add(s)
        db.commit()
        if body.mode and body.mode != s.mode:
            ctx = flow.Ctx(db=db, seller=s, s=sessions.get(seller_id))
            events = flow.ask_confirmation(ctx, flow.mode_request(ctx, body.mode.value))
    if events:
        await notifier.push(seller_id, events)
    await push_board(seller_id)
    return {"ok": True, "requires_confirmation": bool(events)}


@app.post("/api/turn/{seller_id}")
async def turn(seller_id: int, text: str | None = Form(None), button: str | None = Form(None),
               image_id: int | None = Form(None), purpose: str | None = Form(None), confidence: float | None = Form(None),
               latency_ms: int | None = Form(None), audio: UploadFile | None = File(None)):
    if audio:
        import base64
        inp = {"type": "audio", "data": base64.b64encode(await audio.read()).decode()}
    elif image_id:
        inp = {"type": "image", "image_id": image_id, "purpose": purpose}
    elif button:
        inp = {"type": "button", "value": button}
    else:
        inp = {"type": "text", "text": text or "", "confidence": confidence}
    inp["latency_ms"] = latency_ms
    return await run_and_push(seller_id, inp)


@app.post("/api/images")
async def upload_image(file: UploadFile | None = File(None), demo_photo: str | None = Form(None),
                       owner_type: str = Form("listing"), owner_id: int = Form(0)):
    UPLOAD_DIR.mkdir(exist_ok=True)
    obs = {}
    if demo_photo:
        if demo_photo not in catalog.demo_photos():
            raise HTTPException(404, "Không có ảnh mẫu này")
        dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{demo_photo}"
        shutil.copy(PHOTO_DIR / demo_photo, dest)
        obs["_fixture"] = demo_photo
    elif file:
        suffix = Path(file.filename or "photo.jpg").suffix.lower()
        if suffix not in (".jpg", ".jpeg", ".png", ".webp"):
            suffix = ".jpg"
        dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
        dest.write_bytes(await file.read())
    else:
        raise HTTPException(400, "Thiếu ảnh")
    with get_session() as db:
        img = Image(owner_type=owner_type, owner_id=owner_id, path=str(dest), observations=obs)
        db.add(img)
        db.commit()
        return {"image_id": img.id, "url": f"/api/images/{img.id}/file"}


# ---------------- đăng nhanh từ ảnh (Kênh Người Bán, người nhìn được) ----------------

@app.post("/api/quick/{seller_id}")
async def quick_draft(seller_id: int, text: str = Form(""), file: UploadFile | None = File(None),
                      demo_photo: str | None = Form(None)):
    from app.services import shopmaker
    up = await upload_image(file=file, demo_photo=demo_photo, owner_type="listing", owner_id=0)
    with get_session() as db:
        seller = db.get(Seller, seller_id)
        if not seller:
            raise HTTPException(404)
        out = await shopmaker.draft_from_photo(db, seller, db.get(Image, up["image_id"]), text[:500])
        if not out:
            raise HTTPException(422, "Chưa nhận ra sản phẩm trong ảnh (hiện hỗ trợ: mật ong, chè, đồ thủ công, nến, đồ khô)")
        return {**shopmaker.form_view(db, out["listing"]), "price": out["price"], "filled": out["filled"]}


@app.get("/api/quick/{seller_id}/{listing_id}")
def quick_view(seller_id: int, listing_id: int):
    from app.services import shopmaker
    with get_session() as db:
        lst = db.get(Listing, listing_id)
        if not lst or lst.seller_id != seller_id:
            raise HTTPException(404)
        return shopmaker.form_view(db, lst)


class QuickPublishIn(BaseModel):
    values: dict[str, str] = {}


@app.post("/api/quick/{seller_id}/{listing_id}/publish")
async def quick_publish(seller_id: int, listing_id: int, body: QuickPublishIn):
    from app.services import shopmaker
    with get_session() as db:
        lst, seller = db.get(Listing, listing_id), db.get(Seller, seller_id)
        if not lst or not seller or lst.seller_id != seller_id or lst.status not in ("drafting", "ready"):
            raise HTTPException(409, "Tin này không còn ở bản nháp")
        out = await shopmaker.quick_publish(db, seller, lst, body.values, demo=config.DEMO["on"])
    await push_board(seller_id)
    return out


@app.get("/api/images/{image_id}/file")
def image_file(image_id: int):
    with get_session() as db:
        img = db.get(Image, image_id)
        if not img:
            raise HTTPException(404)
        return FileResponse(img.path, headers={"Cache-Control": "no-cache"})   # ảnh quảng cáo có thể được thay tại chỗ


@app.get("/api/listings")
def get_listings(seller_id: int = 1):
    with get_session() as db:
        rows = db.exec(select(Listing).where(Listing.seller_id == seller_id).order_by(Listing.id.desc())).all()
        return [{**public_listing(db, l), "fields": {k: {"value": f.value, "state": f.state.value} for k, f in ls.fields(db, l.id).items()}}
                for l in rows]


@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: int):
    with get_session() as db:
        l = db.get(Listing, listing_id)
        if not l:
            raise HTTPException(404)
        return {**public_listing(db, l), "description_tagged": l.description,
                "fields": [f.model_dump() for f in ls.fields(db, l.id).values()]}


@app.get("/api/orders")
def get_orders(seller_id: int = 1, status: str | None = None):
    with get_session() as db:
        q = select(Order).where(Order.seller_id == seller_id)
        if status:
            q = q.where(Order.status == status)
        return [osv.order_card(db, o) for o in db.exec(q.order_by(Order.id.desc())).all()]


@app.get("/api/messages")
def get_messages(seller_id: int = 1):
    with get_session() as db:
        rows = db.exec(select(BuyerMessage).where(BuyerMessage.seller_id == seller_id).order_by(BuyerMessage.id.desc()).limit(50)).all()
        out = []
        for m in rows:
            lst = db.get(Listing, m.listing_id) if m.listing_id else None
            out.append({"id": m.id, "buyer": m.buyer_name, "text": m.text, "answer": m.answer, "status": m.status,
                        "product": lst.title if lst else None, "at": m.created_at.isoformat(timespec="minutes")})
        return out


@app.get("/api/seller-center/{seller_id}")
def seller_center(seller_id: int):
    """Số liệu tổng quan cho Kênh Người Bán."""
    with get_session() as db:
        s = db.get(Seller, seller_id)
        if not s:
            raise HTTPException(404)
        orders = db.exec(select(Order).where(Order.seller_id == seller_id)).all()
        since = datetime.now() - timedelta(days=30)
        by_status: dict[str, int] = {}
        for o in orders:
            by_status[o.status] = by_status.get(o.status, 0) + 1
        revenue = sum(o.seller_payout for o in orders if o.created_at >= since and o.status != "cancelled")
        days = []
        for i in range(6, -1, -1):
            d = (datetime.now() - timedelta(days=i)).date()
            days.append({"date": d.isoformat(), "orders": sum(1 for o in orders if o.created_at.date() == d),
                         "revenue": sum(o.seller_payout for o in orders if o.created_at.date() == d and o.status != "cancelled")})
        lsts = db.exec(select(Listing).where(Listing.seller_id == seller_id)).all()
        blocked = db.exec(select(func.count()).select_from(BlockedError).where(BlockedError.seller_id == seller_id)).one()
        from app.agent.rt_tools import PROFILE_FIELDS, profile_view
        vals, missing = profile_view(s)
        return {"shop": {"id": s.id, "name": s.shop_name or s.name or "(chưa đặt tên)", "owner": s.name, "avatar": s.avatar, "region": s.region,
                         "followers": s.followers, "assistant": s.uses_assistant, "mode": s.mode.value,
                         "guardian_required": s.guardian_required},
                "profile": {"onboarded": s.onboarded, "missing": [PROFILE_FIELDS[k][0] for k in missing],
                            "fields": [{"key": k, "label": label, "required": req, "value": vals.get(k) or None}
                                       for k, (label, req) in PROFILE_FIELDS.items()]},
                "revenue_30d": revenue, "orders_by_status": by_status, "days": days,
                "products": {"published": sum(1 for l in lsts if l.status == "published"),
                             "drafting": sum(1 for l in lsts if l.status in ("drafting", "ready", "pending_publish")),
                             "low_stock": sum(1 for l in lsts if l.status == "published" and (l.stock or 0) <= s.low_stock_threshold)},
                "waiting_questions": len(support.waiting(db, seller_id)), "blocked_errors": blocked,
                "views_7d": sum(l.views_7d for l in lsts)}


@app.get("/api/config")
def get_config():
    return {"agent_mode": config.AGENT_MODE, "stt": config.STT_PROVIDER, "tts": config.TTS_PROVIDER,
            "llm": bool(config.LLM_MODEL and config.OPENAI_API_KEY)}


# ---------------- bảo trợ ----------------

@app.get("/api/guardian/{seller_id}")
def guardian_list(seller_id: int):
    with get_session() as db:
        rows = db.exec(select(GuardianApproval).where(GuardianApproval.seller_id == seller_id).order_by(GuardianApproval.id.desc()).limit(20)).all()
        return [{"id": g.id, "subject_ref": g.subject_ref, "summary": g.summary, "status": g.status,
                 "card": g.payload.get("card"), "at": g.created_at.isoformat(timespec="minutes")} for g in rows]


class DecideIn(BaseModel):
    approve: bool


@app.post("/api/guardian/approvals/{approval_id}")
async def guardian_decide(approval_id: int, body: DecideIn):
    with get_session() as db:
        ga = db.get(GuardianApproval, approval_id)
        if not ga or ga.status != "waiting":
            raise HTTPException(409, "Không còn chờ duyệt")
        seller = db.get(Seller, ga.seller_id)
        events = await flow.guardian_decide(db, seller, sessions.get(seller.id), ga, body.approve)
    await notifier.push(seller.id, events)
    await push_board(seller.id)
    return {"ok": True}


# ---------------- demo ----------------

@app.get("/api/demo/board/{seller_id}")
def demo_board(seller_id: int):
    return board_snapshot(seller_id)


class DemoModeIn(BaseModel):
    on: bool


@app.get("/api/demo/mode")
def demo_mode():
    return {"on": config.DEMO["on"], "pending_seconds": config.pending_seconds()}


@app.post("/api/demo/mode")
def set_demo_mode(body: DemoModeIn):
    config.DEMO["on"] = body.on
    return demo_mode()


@app.get("/api/demo/photos")
def demo_photos():
    return [{"name": k, "label": v["label"], "url": f"/demo_photos/{k}"} for k, v in catalog.demo_photos().items()]


@app.post("/api/demo/reset")
async def demo_reset():
    reset()
    sessions.reset_all()
    notifier.clear()
    _warned_due.clear()
    await push_board(1)
    return {"ok": True}


class SimOrderIn(BaseModel):
    seller_id: int = 1
    listing: str | int = "latest_honey"
    qty: int = 2
    buyer: str = "Nguyễn Thị Lan"
    province: str = "Hà Nội"
    ship_by_days: int = 2


@app.post("/api/demo/simulate/order")
async def sim_order(body: SimOrderIn):
    with get_session() as db:
        seller = db.get(Seller, body.seller_id)
        lst = simulator.resolve_listing(db, seller.id, body.listing)
        if not lst:
            raise HTTPException(404, "Chưa có tin đang bán")
        o = simulator.spawn_order(db, seller, lst, body.qty, body.buyer, body.province, body.ship_by_days)
        events = simulator.ingest_order(db, seller, o)
    await notifier.push(body.seller_id, events)
    await push_board(body.seller_id)
    return {"order_id": o.id}


class SimMsgIn(BaseModel):
    seller_id: int = 1
    listing: str | int = "latest_honey"
    text: str
    buyer: str = "Khách"


@app.post("/api/demo/simulate/buyer_message")
async def sim_message(body: SimMsgIn):
    with get_session() as db:
        seller = db.get(Seller, body.seller_id)
        lst = simulator.resolve_listing(db, seller.id, body.listing)
        msg, events = simulator.spawn_buyer_message(db, seller, lst, body.text, body.buyer)
        out = {"message_id": msg.id, "status": msg.status, "answer": msg.answer}
    await notifier.push(body.seller_id, events)
    await push_board(body.seller_id)
    return out


@app.post("/api/demo/script/{key}")
async def run_script(key: str, seller_id: int = 1):
    step = next((s for s in simulator.script() if s["key"] == key), None)
    if not step:
        raise HTTPException(404)
    a = step["args"]
    if step["action"] == "spawn_order":
        return await sim_order(SimOrderIn(seller_id=seller_id, **a))
    if step["action"] == "buyer_message":
        return await sim_message(SimMsgIn(seller_id=seller_id, **a))
    if step["action"] == "fast_forward":
        await tick(force_publish=True)
        await push_board(seller_id)
        return {"ok": True}
    if step["action"] == "deliver_shipped":
        with get_session() as db:
            for o in db.exec(select(Order).where(Order.seller_id == seller_id, Order.status == "shipped")).all():
                o.status = "delivered"
                db.add(o)
            db.commit()
        await push_board(seller_id)
        return {"ok": True}
    if step["action"] == "briefing":
        return await run_and_push(seller_id, {"type": "button", "value": "card:today"})
    raise HTTPException(400)


app.mount("/demo_photos", StaticFiles(directory=PHOTO_DIR, check_dir=False), name="demo_photos")

_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
