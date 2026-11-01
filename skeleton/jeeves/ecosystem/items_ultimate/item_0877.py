"""Item ultimate 0877.
"""
from __future__ import annotations

ID = "item_ultimate_0877"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 877, "tier": 877 % 5}

def apply(context: str = "") -> dict:
    if not context and 877 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
