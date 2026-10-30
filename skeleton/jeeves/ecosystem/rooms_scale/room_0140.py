"""Room scale 0140.
"""
from __future__ import annotations

ID = "room_scale_0140"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 140}

def activate(context: str = "") -> dict:
    if not context and 140 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
