"""Room scale 0078.
"""
from __future__ import annotations

ID = "room_scale_0078"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 78}

def activate(context: str = "") -> dict:
    if not context and 78 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
