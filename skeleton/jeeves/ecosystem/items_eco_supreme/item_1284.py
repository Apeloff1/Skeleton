"""Item eco_supreme 1284.
"""
from __future__ import annotations

ID = "item_eco_supreme_1284"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1284, "tier": 1284 % 5}

def apply(context: str = "") -> dict:
    if not context and 1284 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
