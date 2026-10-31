"""Item max 0129.
"""
from __future__ import annotations

ID = "item_max_0129"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 129, "tier": 129 % 5}

def apply(context: str = "") -> dict:
    if not context and 129 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
