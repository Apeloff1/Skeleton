"""Boss scale 0013.
"""
from __future__ import annotations

ID = "boss_scale_0013"

def describe() -> dict:
    return {"id": ID, "kind": "boss", "index": 13}

def activate(context: str = "") -> dict:
    if not context and 13 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
