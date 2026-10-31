"""Item ultra 0234.
"""
from __future__ import annotations

ID = "item_ultra_0234"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 234, "tier": 234 % 5}

def apply(context: str = "") -> dict:
    if not context and 234 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
