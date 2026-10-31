"""Character max 0359.
"""
from __future__ import annotations

ID = "character_max_0359"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 359, "tier": 359 % 5}

def apply(context: str = "") -> dict:
    if not context and 359 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
