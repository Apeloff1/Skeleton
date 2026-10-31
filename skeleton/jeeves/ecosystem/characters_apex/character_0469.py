"""Character apex 0469.
"""
from __future__ import annotations

ID = "character_apex_0469"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 469, "tier": 469 % 5}

def apply(context: str = "") -> dict:
    if not context and 469 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
