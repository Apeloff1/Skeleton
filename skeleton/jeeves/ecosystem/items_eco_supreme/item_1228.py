"""Item eco_supreme 1228.
"""
from __future__ import annotations

ID = "item_eco_supreme_1228"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1228, "tier": 1228 % 5}

def apply(context: str = "") -> dict:
    if not context and 1228 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
