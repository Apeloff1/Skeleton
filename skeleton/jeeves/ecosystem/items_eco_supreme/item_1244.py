"""Item eco_supreme 1244.
"""
from __future__ import annotations

ID = "item_eco_supreme_1244"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1244, "tier": 1244 % 5}

def apply(context: str = "") -> dict:
    if not context and 1244 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
