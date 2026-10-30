"""Item mega 0161.
"""
from __future__ import annotations

ID = "item_mega_0161"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 161, "tier": 161 % 5}

def apply(context: str = "") -> dict:
    if not context and 161 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
