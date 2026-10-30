"""Water advanced 0053.
"""
from __future__ import annotations

ID = "water_adv_0053"

def describe() -> dict:
    return {"id": ID, "kind": "water", "index": 53, "tier": 53 % 5}

def apply(context: str = "") -> dict:
    if not context and 53 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
