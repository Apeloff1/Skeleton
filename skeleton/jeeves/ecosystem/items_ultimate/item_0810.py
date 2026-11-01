"""Item ultimate 0810.
"""
from __future__ import annotations

ID = "item_ultimate_0810"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 810, "tier": 810 % 5}

def apply(context: str = "") -> dict:
    if not context and 810 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
