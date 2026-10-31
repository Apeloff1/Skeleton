"""Item ultra 0277.
"""
from __future__ import annotations

ID = "item_ultra_0277"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 277, "tier": 277 % 5}

def apply(context: str = "") -> dict:
    if not context and 277 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
