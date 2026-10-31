"""Item ultra 0052.
"""
from __future__ import annotations

ID = "item_ultra_0052"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 52, "tier": 52 % 5}

def apply(context: str = "") -> dict:
    if not context and 52 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
