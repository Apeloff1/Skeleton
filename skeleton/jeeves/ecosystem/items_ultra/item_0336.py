"""Item ultra 0336.
"""
from __future__ import annotations

ID = "item_ultra_0336"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 336, "tier": 336 % 5}

def apply(context: str = "") -> dict:
    if not context and 336 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
