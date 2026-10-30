"""Room scale 0114.
"""
from __future__ import annotations

ID = "room_scale_0114"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 114}

def activate(context: str = "") -> dict:
    if not context and 114 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
