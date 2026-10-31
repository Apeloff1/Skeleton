"""Character max 0368.
"""
from __future__ import annotations

ID = "character_max_0368"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 368, "tier": 368 % 5}

def apply(context: str = "") -> dict:
    if not context and 368 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
