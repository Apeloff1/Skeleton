"""Character supreme 0627.
"""
from __future__ import annotations

ID = "character_supreme_0627"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 627, "tier": 627 % 5}

def apply(context: str = "") -> dict:
    if not context and 627 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
