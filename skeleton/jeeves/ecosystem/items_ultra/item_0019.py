"""Item ultra 0019.
"""
from __future__ import annotations

ID = "item_ultra_0019"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 19, "tier": 19 % 5}

def apply(context: str = "") -> dict:
    if not context and 19 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
