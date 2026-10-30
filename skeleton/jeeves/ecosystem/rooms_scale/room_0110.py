"""Room scale 0110.
"""
from __future__ import annotations

ID = "room_scale_0110"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 110}

def activate(context: str = "") -> dict:
    if not context and 110 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
