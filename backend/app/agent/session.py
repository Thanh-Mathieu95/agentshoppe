"""Trạng thái hội thoại theo người bán (trong bộ nhớ, đủ cho demo)."""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from app.confirm.engine import ConfirmationRequest


@dataclass
class Session:
    seller_id: int
    pending: ConfirmationRequest | None = None
    awaiting: tuple | None = None          # ("field", listing_id, key) | ("photo", purpose, ref_id) | ...
    active_listing_id: int | None = None
    active_order_id: int | None = None
    active_message_id: int | None = None
    order_details_read: int | None = None  # đơn vừa được đọc đủ chi tiết (cho phép "nhận đơn" ngay)
    photo_attempts: int = 0
    best_photo_id: int | None = None
    history: list[dict] = field(default_factory=list)   # cho LLM: [{"role","content"}]
    last_events: list[dict] = field(default_factory=list)
    queue: deque = field(default_factory=deque)           # câu hỏi dồn lại, mỗi lượt chỉ hỏi một câu
    greeted: bool = False
    last_turn_at: datetime = field(default_factory=datetime.now)
    heard: list = field(default_factory=list)              # [(thời điểm, lời người bán)] từ nhận dạng giọng realtime
    heard_event: asyncio.Event = field(default_factory=asyncio.Event)
    quick_since: datetime | None = None    # đang chờ ảnh để AI dựng tin đăng (từ lúc này nghe lời mô tả)

    def remember(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})
        del self.history[:-24]


_SESSIONS: dict[int, Session] = {}


def get(seller_id: int) -> Session:
    if seller_id not in _SESSIONS:
        _SESSIONS[seller_id] = Session(seller_id=seller_id)
    return _SESSIONS[seller_id]


def reset_all() -> None:
    _SESSIONS.clear()
