"""Boss scale 0071.
"""
from __future__ import annotations

ID = "boss_scale_0071"

def describe() -> dict:
    return {"id": ID, "kind": "boss", "index": 71}

def activate(context: str = "") -> dict:
    if not context and 71 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
