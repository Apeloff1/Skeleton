"""Item ultra 0310.
"""
from __future__ import annotations

ID = "item_ultra_0310"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 310, "tier": 310 % 5}

def apply(context: str = "") -> dict:
    if not context and 310 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
