"""Item eco_supreme 0433.
"""
from __future__ import annotations

ID = "item_eco_supreme_0433"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 433, "tier": 433 % 5}

def apply(context: str = "") -> dict:
    if not context and 433 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
