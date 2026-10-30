"""Room scale 0122.
"""
from __future__ import annotations

ID = "room_scale_0122"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 122}

def activate(context: str = "") -> dict:
    if not context and 122 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
