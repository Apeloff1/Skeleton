"""Item mega 0214.
"""
from __future__ import annotations

ID = "item_mega_0214"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 214, "tier": 214 % 5}

def apply(context: str = "") -> dict:
    if not context and 214 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
