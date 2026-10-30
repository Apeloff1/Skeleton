"""Item mega 0203.
"""
from __future__ import annotations

ID = "item_mega_0203"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 203, "tier": 203 % 5}

def apply(context: str = "") -> dict:
    if not context and 203 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
