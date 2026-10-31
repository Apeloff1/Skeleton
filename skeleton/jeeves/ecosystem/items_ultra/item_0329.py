"""Item ultra 0329.
"""
from __future__ import annotations

ID = "item_ultra_0329"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 329, "tier": 329 % 5}

def apply(context: str = "") -> dict:
    if not context and 329 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
