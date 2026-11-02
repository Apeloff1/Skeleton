"""Item eco_supreme 0088.
"""
from __future__ import annotations

ID = "item_eco_supreme_0088"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 88, "tier": 88 % 5}

def apply(context: str = "") -> dict:
    if not context and 88 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
