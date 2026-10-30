"""Item mega 0002.
"""
from __future__ import annotations

ID = "item_mega_0002"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 2, "tier": 2 % 5}

def apply(context: str = "") -> dict:
    if not context and 2 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
