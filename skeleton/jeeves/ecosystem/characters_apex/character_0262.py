"""Character apex 0262.
"""
from __future__ import annotations

ID = "character_apex_0262"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 262, "tier": 262 % 5}

def apply(context: str = "") -> dict:
    if not context and 262 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
