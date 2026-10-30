"""Item mega 0079.
"""
from __future__ import annotations

ID = "item_mega_0079"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 79, "tier": 79 % 5}

def apply(context: str = "") -> dict:
    if not context and 79 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
