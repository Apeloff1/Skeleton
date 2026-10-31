"""Character max 0357.
"""
from __future__ import annotations

ID = "character_max_0357"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 357, "tier": 357 % 5}

def apply(context: str = "") -> dict:
    if not context and 357 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
