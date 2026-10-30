"""Item mega 0114.
"""
from __future__ import annotations

ID = "item_mega_0114"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 114, "tier": 114 % 5}

def apply(context: str = "") -> dict:
    if not context and 114 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
