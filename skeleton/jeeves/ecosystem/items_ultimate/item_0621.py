"""Item ultimate 0621.
"""
from __future__ import annotations

ID = "item_ultimate_0621"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 621, "tier": 621 % 5}

def apply(context: str = "") -> dict:
    if not context and 621 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
