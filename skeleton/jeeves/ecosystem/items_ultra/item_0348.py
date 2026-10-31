"""Item ultra 0348.
"""
from __future__ import annotations

ID = "item_ultra_0348"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 348, "tier": 348 % 5}

def apply(context: str = "") -> dict:
    if not context and 348 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
