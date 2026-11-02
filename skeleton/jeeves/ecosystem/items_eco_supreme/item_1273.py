"""Item eco_supreme 1273.
"""
from __future__ import annotations

ID = "item_eco_supreme_1273"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1273, "tier": 1273 % 5}

def apply(context: str = "") -> dict:
    if not context and 1273 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
