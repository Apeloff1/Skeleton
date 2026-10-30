"""Item mega 0294.
"""
from __future__ import annotations

ID = "item_mega_0294"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 294, "tier": 294 % 5}

def apply(context: str = "") -> dict:
    if not context and 294 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
