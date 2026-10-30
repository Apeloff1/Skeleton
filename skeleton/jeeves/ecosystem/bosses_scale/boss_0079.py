"""Boss scale 0079.
"""
from __future__ import annotations

ID = "boss_scale_0079"

def describe() -> dict:
    return {"id": ID, "kind": "boss", "index": 79}

def activate(context: str = "") -> dict:
    if not context and 79 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
