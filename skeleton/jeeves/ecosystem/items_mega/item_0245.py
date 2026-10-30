"""Item mega 0245.
"""
from __future__ import annotations

ID = "item_mega_0245"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 245, "tier": 245 % 5}

def apply(context: str = "") -> dict:
    if not context and 245 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
