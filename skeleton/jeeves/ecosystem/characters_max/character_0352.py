"""Character max 0352.
"""
from __future__ import annotations

ID = "character_max_0352"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 352, "tier": 352 % 5}

def apply(context: str = "") -> dict:
    if not context and 352 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
