"""Item ultra 0085.
"""
from __future__ import annotations

ID = "item_ultra_0085"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 85, "tier": 85 % 5}

def apply(context: str = "") -> dict:
    if not context and 85 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
