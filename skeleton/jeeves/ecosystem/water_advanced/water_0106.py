"""Water advanced 0106.
"""
from __future__ import annotations

ID = "water_adv_0106"

def describe() -> dict:
    return {"id": ID, "kind": "water", "index": 106, "tier": 106 % 5}

def apply(context: str = "") -> dict:
    if not context and 106 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
