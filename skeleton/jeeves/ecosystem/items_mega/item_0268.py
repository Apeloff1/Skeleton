"""Item mega 0268.
"""
from __future__ import annotations

ID = "item_mega_0268"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 268, "tier": 268 % 5}

def apply(context: str = "") -> dict:
    if not context and 268 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
