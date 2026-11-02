"""Item eco_supreme 1039.
"""
from __future__ import annotations

ID = "item_eco_supreme_1039"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1039, "tier": 1039 % 5}

def apply(context: str = "") -> dict:
    if not context and 1039 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
