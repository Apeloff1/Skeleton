"""Item max 0360.
"""
from __future__ import annotations

ID = "item_max_0360"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 360, "tier": 360 % 5}

def apply(context: str = "") -> dict:
    if not context and 360 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
