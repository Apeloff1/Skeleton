"""Item ultra 0241.
"""
from __future__ import annotations

ID = "item_ultra_0241"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 241, "tier": 241 % 5}

def apply(context: str = "") -> dict:
    if not context and 241 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
