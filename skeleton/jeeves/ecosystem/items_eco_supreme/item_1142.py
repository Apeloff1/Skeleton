"""Item eco_supreme 1142.
"""
from __future__ import annotations

ID = "item_eco_supreme_1142"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1142, "tier": 1142 % 5}

def apply(context: str = "") -> dict:
    if not context and 1142 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
