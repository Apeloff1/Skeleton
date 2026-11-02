"""Item eco_supreme 0909.
"""
from __future__ import annotations

ID = "item_eco_supreme_0909"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 909, "tier": 909 % 5}

def apply(context: str = "") -> dict:
    if not context and 909 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
