"""Item mega 0281.
"""
from __future__ import annotations

ID = "item_mega_0281"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 281, "tier": 281 % 5}

def apply(context: str = "") -> dict:
    if not context and 281 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
