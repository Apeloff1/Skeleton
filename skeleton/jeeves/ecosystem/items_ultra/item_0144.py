"""Item ultra 0144.
"""
from __future__ import annotations

ID = "item_ultra_0144"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 144, "tier": 144 % 5}

def apply(context: str = "") -> dict:
    if not context and 144 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
