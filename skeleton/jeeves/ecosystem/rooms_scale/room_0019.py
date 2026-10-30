"""Room scale 0019.
"""
from __future__ import annotations

ID = "room_scale_0019"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 19}

def activate(context: str = "") -> dict:
    if not context and 19 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
