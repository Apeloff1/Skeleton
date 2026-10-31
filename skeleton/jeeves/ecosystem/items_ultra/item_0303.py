"""Item ultra 0303.
"""
from __future__ import annotations

ID = "item_ultra_0303"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 303, "tier": 303 % 5}

def apply(context: str = "") -> dict:
    if not context and 303 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
