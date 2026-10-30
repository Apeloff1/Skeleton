"""Boss scale 0076.
"""
from __future__ import annotations

ID = "boss_scale_0076"

def describe() -> dict:
    return {"id": ID, "kind": "boss", "index": 76}

def activate(context: str = "") -> dict:
    if not context and 76 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
