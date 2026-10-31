"""Item ultra 0145.
"""
from __future__ import annotations

ID = "item_ultra_0145"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 145, "tier": 145 % 5}

def apply(context: str = "") -> dict:
    if not context and 145 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
