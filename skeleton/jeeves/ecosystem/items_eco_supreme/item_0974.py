"""Item eco_supreme 0974.
"""
from __future__ import annotations

ID = "item_eco_supreme_0974"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 974, "tier": 974 % 5}

def apply(context: str = "") -> dict:
    if not context and 974 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
