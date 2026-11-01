"""Character supreme 0491.
"""
from __future__ import annotations

ID = "character_supreme_0491"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 491, "tier": 491 % 5}

def apply(context: str = "") -> dict:
    if not context and 491 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
