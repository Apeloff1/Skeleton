"""Character max 0378.
"""
from __future__ import annotations

ID = "character_max_0378"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 378, "tier": 378 % 5}

def apply(context: str = "") -> dict:
    if not context and 378 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
