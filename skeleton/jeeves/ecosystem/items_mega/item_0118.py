"""Item mega 0118.
"""
from __future__ import annotations

ID = "item_mega_0118"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 118, "tier": 118 % 5}

def apply(context: str = "") -> dict:
    if not context and 118 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
