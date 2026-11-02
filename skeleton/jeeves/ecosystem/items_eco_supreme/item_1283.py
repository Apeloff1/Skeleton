"""Item eco_supreme 1283.
"""
from __future__ import annotations

ID = "item_eco_supreme_1283"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1283, "tier": 1283 % 5}

def apply(context: str = "") -> dict:
    if not context and 1283 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
