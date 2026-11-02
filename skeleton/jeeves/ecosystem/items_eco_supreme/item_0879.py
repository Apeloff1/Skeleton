"""Item eco_supreme 0879.
"""
from __future__ import annotations

ID = "item_eco_supreme_0879"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 879, "tier": 879 % 5}

def apply(context: str = "") -> dict:
    if not context and 879 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
