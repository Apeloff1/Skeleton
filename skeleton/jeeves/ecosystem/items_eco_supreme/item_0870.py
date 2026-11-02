"""Item eco_supreme 0870.
"""
from __future__ import annotations

ID = "item_eco_supreme_0870"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 870, "tier": 870 % 5}

def apply(context: str = "") -> dict:
    if not context and 870 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
