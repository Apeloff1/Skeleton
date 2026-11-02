"""Item eco_supreme 0919.
"""
from __future__ import annotations

ID = "item_eco_supreme_0919"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 919, "tier": 919 % 5}

def apply(context: str = "") -> dict:
    if not context and 919 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
