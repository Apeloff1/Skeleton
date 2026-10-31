"""Item max 0340.
"""
from __future__ import annotations

ID = "item_max_0340"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 340, "tier": 340 % 5}

def apply(context: str = "") -> dict:
    if not context and 340 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
