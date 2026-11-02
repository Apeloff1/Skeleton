"""Item eco_supreme 1299.
"""
from __future__ import annotations

ID = "item_eco_supreme_1299"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1299, "tier": 1299 % 5}

def apply(context: str = "") -> dict:
    if not context and 1299 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
