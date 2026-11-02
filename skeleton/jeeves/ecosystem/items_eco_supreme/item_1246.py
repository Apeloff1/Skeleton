"""Item eco_supreme 1246.
"""
from __future__ import annotations

ID = "item_eco_supreme_1246"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1246, "tier": 1246 % 5}

def apply(context: str = "") -> dict:
    if not context and 1246 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
