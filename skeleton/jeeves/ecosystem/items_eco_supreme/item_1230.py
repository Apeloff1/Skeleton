"""Item eco_supreme 1230.
"""
from __future__ import annotations

ID = "item_eco_supreme_1230"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1230, "tier": 1230 % 5}

def apply(context: str = "") -> dict:
    if not context and 1230 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
