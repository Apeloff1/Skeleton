"""Room scale 0051.
"""
from __future__ import annotations

ID = "room_scale_0051"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 51}

def activate(context: str = "") -> dict:
    if not context and 51 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
