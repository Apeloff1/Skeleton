"""Character max 0377.
"""
from __future__ import annotations

ID = "character_max_0377"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 377, "tier": 377 % 5}

def apply(context: str = "") -> dict:
    if not context and 377 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
