"""Item eco_supreme 1288.
"""
from __future__ import annotations

ID = "item_eco_supreme_1288"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1288, "tier": 1288 % 5}

def apply(context: str = "") -> dict:
    if not context and 1288 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
