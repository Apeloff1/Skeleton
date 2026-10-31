"""Item ultra 0187.
"""
from __future__ import annotations

ID = "item_ultra_0187"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 187, "tier": 187 % 5}

def apply(context: str = "") -> dict:
    if not context and 187 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
