"""Item ultimate 0524.
"""
from __future__ import annotations

ID = "item_ultimate_0524"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 524, "tier": 524 % 5}

def apply(context: str = "") -> dict:
    if not context and 524 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
