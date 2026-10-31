"""Item ultra 0274.
"""
from __future__ import annotations

ID = "item_ultra_0274"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 274, "tier": 274 % 5}

def apply(context: str = "") -> dict:
    if not context and 274 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
