"""Room scale 0091.
"""
from __future__ import annotations

ID = "room_scale_0091"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 91}

def activate(context: str = "") -> dict:
    if not context and 91 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
