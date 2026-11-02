"""Item eco_supreme 1206.
"""
from __future__ import annotations

ID = "item_eco_supreme_1206"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1206, "tier": 1206 % 5}

def apply(context: str = "") -> dict:
    if not context and 1206 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
