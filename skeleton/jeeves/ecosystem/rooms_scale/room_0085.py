"""Room scale 0085.
"""
from __future__ import annotations

ID = "room_scale_0085"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 85}

def activate(context: str = "") -> dict:
    if not context and 85 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
