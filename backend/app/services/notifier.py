"""Đẩy sự kiện tới điện thoại người bán, màn hình bảo trợ và DemoBoard qua WebSocket."""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime

from fastapi import WebSocket

log = logging.getLogger(__name__)

_sellers: dict[int, set[WebSocket]] = defaultdict(set)
_boards: dict[int, set[WebSocket]] = defaultdict(set)
_subtitles: dict[int, deque] = defaultdict(lambda: deque(maxlen=80))


def connect(seller_id: int, ws: WebSocket, board: bool = False) -> None:
    (_boards if board else _sellers)[seller_id].add(ws)


def disconnect(seller_id: int, ws: WebSocket) -> None:
    _sellers[seller_id].discard(ws)
    _boards[seller_id].discard(ws)


def subtitle(seller_id: int, who: str, text: str) -> None:
    if text:
        _subtitles[seller_id].append({"who": who, "text": text, "at": datetime.now().isoformat(timespec="seconds")})


def subtitles(seller_id: int) -> list[dict]:
    return list(_subtitles[seller_id])


def clear() -> None:
    _subtitles.clear()


async def _send(sockets: set[WebSocket], msg: dict) -> None:
    dead = []
    for ws in list(sockets):
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        sockets.discard(ws)


async def push(seller_id: int, events: list[dict]) -> None:
    for e in events:   # tuần tự: thứ tự câu nói và thẻ phải giữ nguyên
        if e.get("type") == "speak":
            subtitle(seller_id, "agent", e["text"])
        elif e.get("type") == "notify":
            subtitle(seller_id, "system", e["payload"].get("text", e["kind"]))
        await _send(_sellers[seller_id], e)


async def push_board(seller_id: int, payload: dict) -> None:
    await _send(_boards[seller_id], {"type": "board_update", "payload": payload})


def has_board(seller_id: int) -> bool:
    return bool(_boards[seller_id])
