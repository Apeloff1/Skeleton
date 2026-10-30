"""Item mega 0108.
"""
from __future__ import annotations

ID = "item_mega_0108"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 108, "tier": 108 % 5}

def apply(context: str = "") -> dict:
    if not context and 108 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
