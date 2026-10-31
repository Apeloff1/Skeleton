"""Item ultra 0304.
"""
from __future__ import annotations

ID = "item_ultra_0304"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 304, "tier": 304 % 5}

def apply(context: str = "") -> dict:
    if not context and 304 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
