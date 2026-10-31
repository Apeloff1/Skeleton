"""Item ultra 0308.
"""
from __future__ import annotations

ID = "item_ultra_0308"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 308, "tier": 308 % 5}

def apply(context: str = "") -> dict:
    if not context and 308 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
