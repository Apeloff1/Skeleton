"""Item eco_supreme 1247.
"""
from __future__ import annotations

ID = "item_eco_supreme_1247"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1247, "tier": 1247 % 5}

def apply(context: str = "") -> dict:
    if not context and 1247 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
