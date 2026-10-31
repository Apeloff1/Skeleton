"""Character max 0381.
"""
from __future__ import annotations

ID = "character_max_0381"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 381, "tier": 381 % 5}

def apply(context: str = "") -> dict:
    if not context and 381 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
