"""Item mega 0175.
"""
from __future__ import annotations

ID = "item_mega_0175"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 175, "tier": 175 % 5}

def apply(context: str = "") -> dict:
    if not context and 175 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
