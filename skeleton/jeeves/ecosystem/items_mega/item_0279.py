"""Item mega 0279.
"""
from __future__ import annotations

ID = "item_mega_0279"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 279, "tier": 279 % 5}

def apply(context: str = "") -> dict:
    if not context and 279 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
