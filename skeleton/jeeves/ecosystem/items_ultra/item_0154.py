"""Item ultra 0154.
"""
from __future__ import annotations

ID = "item_ultra_0154"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 154, "tier": 154 % 5}

def apply(context: str = "") -> dict:
    if not context and 154 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
