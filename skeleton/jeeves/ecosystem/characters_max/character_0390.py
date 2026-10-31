"""Character max 0390.
"""
from __future__ import annotations

ID = "character_max_0390"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 390, "tier": 390 % 5}

def apply(context: str = "") -> dict:
    if not context and 390 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
