"""Item ultra 0288.
"""
from __future__ import annotations

ID = "item_ultra_0288"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 288, "tier": 288 % 5}

def apply(context: str = "") -> dict:
    if not context and 288 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
