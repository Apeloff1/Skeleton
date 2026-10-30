"""Room scale 0095.
"""
from __future__ import annotations

ID = "room_scale_0095"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 95}

def activate(context: str = "") -> dict:
    if not context and 95 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
