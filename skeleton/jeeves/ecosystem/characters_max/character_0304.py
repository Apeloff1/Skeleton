"""Character max 0304.
"""
from __future__ import annotations

ID = "character_max_0304"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 304, "tier": 304 % 5}

def apply(context: str = "") -> dict:
    if not context and 304 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
