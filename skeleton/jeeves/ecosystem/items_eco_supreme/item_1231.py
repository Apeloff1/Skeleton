"""Item eco_supreme 1231.
"""
from __future__ import annotations

ID = "item_eco_supreme_1231"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1231, "tier": 1231 % 5}

def apply(context: str = "") -> dict:
    if not context and 1231 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
