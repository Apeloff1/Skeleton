"""Item eco_supreme 1252.
"""
from __future__ import annotations

ID = "item_eco_supreme_1252"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1252, "tier": 1252 % 5}

def apply(context: str = "") -> dict:
    if not context and 1252 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
