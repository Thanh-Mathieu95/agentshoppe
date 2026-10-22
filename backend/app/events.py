"""Sự kiện server -> client (mục 15)."""


def speak(text: str, priority: str = "normal") -> dict:
    return {"type": "speak", "text": text, "priority": priority}


def card(**card) -> dict:
    return {"type": "card", "card": card}


def notify(kind: str, payload: dict, vibrate: list[int] | None = None) -> dict:
    return {"type": "notify", "kind": kind, "payload": payload, "vibrate": vibrate or [200, 100, 200]}


def open_camera(purpose: str, guide: str, ref_id: int | None = None) -> dict:
    return {"type": "open_camera", "purpose": purpose, "guide": guide, "ref_id": ref_id}


def res(ok: bool = True, say: str | None = None, warnings: list | None = None, confirmation=None,
        data: dict | None = None, events: list | None = None) -> dict:
    """Kết quả chuẩn của mọi công cụ (mục 8)."""
    return {"ok": ok, "say": say, "warnings": warnings or [], "requires_confirmation": confirmation is not None,
            "confirmation": confirmation, "data": data or {}, "events": events or []}


def text_of(events: list[dict]) -> str:
    return " ".join(e["text"] for e in events if e.get("type") == "speak")
