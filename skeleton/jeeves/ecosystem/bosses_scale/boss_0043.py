"""Boss scale 0043.
"""
from __future__ import annotations

ID = "boss_scale_0043"

def describe() -> dict:
    return {"id": ID, "kind": "boss", "index": 43}

def activate(context: str = "") -> dict:
    if not context and 43 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
