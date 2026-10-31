"""Item ultra 0332.
"""
from __future__ import annotations

ID = "item_ultra_0332"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 332, "tier": 332 % 5}

def apply(context: str = "") -> dict:
    if not context and 332 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
