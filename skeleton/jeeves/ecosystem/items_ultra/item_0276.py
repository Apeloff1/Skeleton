"""Item ultra 0276.
"""
from __future__ import annotations

ID = "item_ultra_0276"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 276, "tier": 276 % 5}

def apply(context: str = "") -> dict:
    if not context and 276 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
