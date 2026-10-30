"""Room scale 0145.
"""
from __future__ import annotations

ID = "room_scale_0145"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 145}

def activate(context: str = "") -> dict:
    if not context and 145 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
