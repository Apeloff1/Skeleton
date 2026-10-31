"""Item ultra 0053.
"""
from __future__ import annotations

ID = "item_ultra_0053"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 53, "tier": 53 % 5}

def apply(context: str = "") -> dict:
    if not context and 53 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
