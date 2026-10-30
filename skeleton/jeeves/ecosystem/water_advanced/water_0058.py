"""Water advanced 0058.
"""
from __future__ import annotations

ID = "water_adv_0058"

def describe() -> dict:
    return {"id": ID, "kind": "water", "index": 58, "tier": 58 % 5}

def apply(context: str = "") -> dict:
    if not context and 58 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
