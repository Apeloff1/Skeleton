"""Water advanced 0110.
"""
from __future__ import annotations

ID = "water_adv_0110"

def describe() -> dict:
    return {"id": ID, "kind": "water", "index": 110, "tier": 110 % 5}

def apply(context: str = "") -> dict:
    if not context and 110 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
