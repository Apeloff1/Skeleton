"""Item ultra 0179.
"""
from __future__ import annotations

ID = "item_ultra_0179"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 179, "tier": 179 % 5}

def apply(context: str = "") -> dict:
    if not context and 179 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
