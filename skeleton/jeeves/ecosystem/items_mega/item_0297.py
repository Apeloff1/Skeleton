"""Item mega 0297.
"""
from __future__ import annotations

ID = "item_mega_0297"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 297, "tier": 297 % 5}

def apply(context: str = "") -> dict:
    if not context and 297 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
