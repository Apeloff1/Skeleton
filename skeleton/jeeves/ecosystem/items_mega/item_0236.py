"""Item mega 0236.
"""
from __future__ import annotations

ID = "item_mega_0236"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 236, "tier": 236 % 5}

def apply(context: str = "") -> dict:
    if not context and 236 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
