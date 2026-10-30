"""Item mega 0167.
"""
from __future__ import annotations

ID = "item_mega_0167"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 167, "tier": 167 % 5}

def apply(context: str = "") -> dict:
    if not context and 167 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
