"""Water advanced 0056.
"""
from __future__ import annotations

ID = "water_adv_0056"

def describe() -> dict:
    return {"id": ID, "kind": "water", "index": 56, "tier": 56 % 5}

def apply(context: str = "") -> dict:
    if not context and 56 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
