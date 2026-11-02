"""Item eco_supreme 1229.
"""
from __future__ import annotations

ID = "item_eco_supreme_1229"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1229, "tier": 1229 % 5}

def apply(context: str = "") -> dict:
    if not context and 1229 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
