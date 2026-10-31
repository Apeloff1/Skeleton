"""Item ultra 0318.
"""
from __future__ import annotations

ID = "item_ultra_0318"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 318, "tier": 318 % 5}

def apply(context: str = "") -> dict:
    if not context and 318 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
