"""Item eco_supreme 1212.
"""
from __future__ import annotations

ID = "item_eco_supreme_1212"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1212, "tier": 1212 % 5}

def apply(context: str = "") -> dict:
    if not context and 1212 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
