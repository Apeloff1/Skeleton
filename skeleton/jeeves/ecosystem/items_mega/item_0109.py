"""Item mega 0109.
"""
from __future__ import annotations

ID = "item_mega_0109"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 109, "tier": 109 % 5}

def apply(context: str = "") -> dict:
    if not context and 109 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
