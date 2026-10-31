"""Item max 0323.
"""
from __future__ import annotations

ID = "item_max_0323"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 323, "tier": 323 % 5}

def apply(context: str = "") -> dict:
    if not context and 323 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
