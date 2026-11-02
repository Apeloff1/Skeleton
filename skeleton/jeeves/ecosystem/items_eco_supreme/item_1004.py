"""Item eco_supreme 1004.
"""
from __future__ import annotations

ID = "item_eco_supreme_1004"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1004, "tier": 1004 % 5}

def apply(context: str = "") -> dict:
    if not context and 1004 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
