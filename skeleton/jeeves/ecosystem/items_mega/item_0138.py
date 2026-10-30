"""Item mega 0138.
"""
from __future__ import annotations

ID = "item_mega_0138"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 138, "tier": 138 % 5}

def apply(context: str = "") -> dict:
    if not context and 138 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
