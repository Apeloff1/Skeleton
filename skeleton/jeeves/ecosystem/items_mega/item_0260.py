"""Item mega 0260.
"""
from __future__ import annotations

ID = "item_mega_0260"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 260, "tier": 260 % 5}

def apply(context: str = "") -> dict:
    if not context and 260 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
