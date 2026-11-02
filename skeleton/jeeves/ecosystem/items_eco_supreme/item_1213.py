"""Item eco_supreme 1213.
"""
from __future__ import annotations

ID = "item_eco_supreme_1213"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1213, "tier": 1213 % 5}

def apply(context: str = "") -> dict:
    if not context and 1213 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
