"""Item max 0398.
"""
from __future__ import annotations

ID = "item_max_0398"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 398, "tier": 398 % 5}

def apply(context: str = "") -> dict:
    if not context and 398 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
