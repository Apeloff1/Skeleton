"""Item mega 0094.
"""
from __future__ import annotations

ID = "item_mega_0094"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 94, "tier": 94 % 5}

def apply(context: str = "") -> dict:
    if not context and 94 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
