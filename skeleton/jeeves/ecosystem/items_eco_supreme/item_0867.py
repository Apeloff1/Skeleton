"""Item eco_supreme 0867.
"""
from __future__ import annotations

ID = "item_eco_supreme_0867"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 867, "tier": 867 % 5}

def apply(context: str = "") -> dict:
    if not context and 867 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
