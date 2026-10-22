"""Vòng lặp một lượt (mục 7.1)."""
from __future__ import annotations

import base64
import json
import logging
import re

from app.agent import flow, llm, prompts, router, session, tools
from app.config import MAX_TOOL_STEPS
from app.confirm.engine import log_confirmation
from app.db import get_session
from app.events import speak
from app.models import Seller
from app.services import listings as ls
from app.services import notifier, orders as osv, support
from app.speech import stt, tts

log = logging.getLogger(__name__)
CONTROL_BUTTONS = {"yes_hold", "no", "repeat", "slower", "stop", "timeout"}


def build_state_summary(ctx: flow.Ctx) -> str:
    db, s = ctx.db, ctx.s
    lines = []
    lst = db.get(ls.Listing, s.active_listing_id) if s.active_listing_id else ls.active_listing(db, ctx.seller.id)
    if lst:
        fs = ", ".join(f"{k}={f.value or '-'}({f.state.value})" for k, f in ls.fields(db, lst.id).items())
        lines.append(f"Phiếu đang làm: listing_id={lst.id}, ngành={lst.category}, trạng thái={lst.status}, "
                     f"ảnh={'có' if ls.has_accepted_photo(db, lst) else 'chưa'}; trường: {fs}")
    if s.active_order_id:
        o = db.get(osv.Order, s.active_order_id)
        if o:
            lines.append(f"Đơn đang xem: order_id={o.id}, {o.buyer_name}, trạng thái={o.status}")
    opens = osv.open_orders(db, ctx.seller.id)
    lines.append(f"Đơn đang mở: {len(opens)} (" + ", ".join(f"#{o.id} {o.status}" for o in opens[:5]) + ")")
    w = support.waiting(db, ctx.seller.id)
    if w:
        lines.append(f"Khách chờ trả lời: {len(w)} (message_id đầu tiên={w[0].id}: '{w[0].text}')")
    if s.active_message_id:
        lines.append(f"Câu hỏi khách đang xử lý: message_id={s.active_message_id}")
    return "\n".join(lines) or "Chưa có gì."


def render_reply(text: str) -> str:
    """Mỗi lượt chỉ một câu hỏi: giữ tới câu hỏi đầu tiên, tối đa 3 câu."""
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if x.strip()]
    out = []
    for x in sentences[:3]:
        out.append(x)
        if x.endswith("?"):
            break
    return " ".join(out)


async def llm_turn(ctx: flow.Ctx) -> list[dict]:
    msgs = prompts.build(ctx.seller.mode.value, ctx.seller.name, ctx.h, build_state_summary(ctx), ctx.s.history, ctx.text)
    extra: list[dict] = []
    final = ""
    for _ in range(MAX_TOOL_STEPS):
        m = await llm.chat(msgs, tools=tools.SCHEMAS)
        if not m.tool_calls:
            final = m.content or ""
            break
        msgs.append({"role": "assistant", "content": m.content or "",
                     "tool_calls": [{"id": c.id, "type": "function",
                                     "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in m.tool_calls]})
        confirmation = None
        said = []
        for c in m.tool_calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            out = await tools.dispatch(c.function.name, args, ctx)
            log.info("tool %s(%s) -> ok=%s", c.function.name, args, out["ok"])
            msgs.append({"role": "tool", "tool_call_id": c.id,
                         "content": json.dumps(tools.for_llm(out), ensure_ascii=False, default=str)})
            extra += out.get("events") or []
            if out.get("say") and c.function.name in ("price_check", "get_order"):
                said.append(speak(out["say"]))
            if out["requires_confirmation"] and confirmation is None:
                confirmation = out["confirmation"]
        if confirmation:
            ctx.s.remember("user", ctx.text)
            ctx.s.remember("assistant", confirmation.prompt_text)
            # Đang chờ xác nhận: LLM dừng, Confirmation Engine tiếp quản.
            if confirmation.kind == "field":
                lst = ctx.db.get(ls.Listing, int(confirmation.subject_ref.split(":")[1]))
                return said + await flow.continue_listing(ctx, lst)
            return said + flow.ask_confirmation(ctx, confirmation)
    ctx.s.remember("user", ctx.text)
    reply = render_reply(final) or "Tôi chưa hiểu. Cô nói lại giúp tôi nhé."
    ctx.s.remember("assistant", reply)
    return [speak(reply)] + extra


async def _attach_audio(events: list[dict], speed: float) -> None:
    if not tts.enabled():
        return
    for e in events:
        if e.get("type") == "speak":
            try:
                rate = speed * (0.9 if e.get("priority") == "confirm" else 1.0)
                e["audio"] = base64.b64encode(await tts.synthesize(e["text"], rate)).decode()
            except Exception as ex:
                log.warning("tts failed: %s", ex)


async def handle_turn(seller_id: int, inp: dict) -> list[dict]:
    typ = inp.get("type")
    with get_session() as db:
        seller = db.get(Seller, seller_id)
        if not seller:
            return [speak("Không tìm thấy người bán.")]
        s = session.get(seller_id)
        text, conf = inp.get("text") or "", inp.get("confidence")
        if typ == "audio":
            asked = (s.pending.prompt_text if s.pending else
                     " ".join(e["text"] for e in s.last_events if e.get("type") == "speak"))[-300:]
            tr = await stt.transcribe(base64.b64decode(inp["data"]),
                                      prompt=stt.PROMPT + (f" Trợ lý vừa hỏi: {asked}" if asked else ""))
            text, conf = tr.text, tr.confidence
            if not text:
                return [speak("Tôi chưa nghe rõ. Cô nói lại giúp tôi nhé.")]
        button = inp.get("value") if typ == "button" else ("timeout" if typ == "timeout" else None)
        ctx = flow.Ctx(db=db, seller=seller, s=s, text=text, button=button, confidence=conf, latency_ms=inp.get("latency_ms"))
        notifier.subtitle(seller_id, "seller", text or ({"yes_hold": "[giữ ĐÚNG]", "no": "[SAI]"}.get(button, f"[{button}]") if button else "")
                          or ("[ảnh]" if typ == "image" else ""))

        if button in ("hello", "next_task"):   # mở app / hỏi việc tiếp: nhắc lại việc đang dở, không bỏ
            events = await flow.next_task(ctx, greet=button == "hello")
            s.greeted = True
            return await _finish(events, s, seller, audio=not inp.get("realtime"))
        if s.pending and (typ == "image" or (button and button not in CONTROL_BUTTONS)):
            log_confirmation(db, s.pending, "unclear", text or button or "image", None)
            s.pending = None   # người bán chuyển sang việc khác; không bao giờ coi là đồng ý
        if s.pending:
            events = await flow.handle_pending(ctx)
        elif typ == "image":
            events = await flow.on_image(ctx, int(inp["image_id"]), inp.get("purpose") or "listing")
        elif typ == "button":
            events = await flow.route_button(ctx)
        elif typ == "timeout":
            events = []
        elif router.use_llm(ctx):
            try:
                events = await llm_turn(ctx)
            except Exception as e:
                log.exception("llm turn failed, fallback to rules: %s", e)
                events = await flow.route_rules(ctx)
        else:
            events = await flow.route_rules(ctx)

        if not s.greeted and not events and typ != "timeout":
            events = [ctx.say("greeting", name=seller.name.split()[-1])]
        s.greeted = True
        return await _finish(events, s, seller, audio=not inp.get("realtime"))


async def _finish(events: list[dict], s, seller, audio: bool = True) -> list[dict]:
    for e in events:
        if e.get("type") == "speak":
            e["speed"] = seller.tts_speed
    if any(e.get("type") == "speak" for e in events):
        s.last_events = [e for e in events if e.get("type") in ("speak", "card", "open_camera")]
    if audio:   # hội thoại realtime tự đọc bằng giọng của nó, không cần tạo âm thanh ở đây
        await _attach_audio(events, seller.tts_speed)
    events.append({"type": "turn_end", "pending": {
        "confirm_id": s.pending.id, "subject_ref": s.pending.subject_ref, "two_step": s.pending.two_step,
        "risk": s.pending.risk.value} if s.pending else None})
    return events
