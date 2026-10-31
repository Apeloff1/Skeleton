"""Item ultra 0075.
"""
from __future__ import annotations

ID = "item_ultra_0075"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 75, "tier": 75 % 5}

def apply(context: str = "") -> dict:
    if not context and 75 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
