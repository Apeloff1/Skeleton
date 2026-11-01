"""Character ultimate 0252.
"""
from __future__ import annotations

ID = "character_ultimate_0252"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 252, "tier": 252 % 5}

def apply(context: str = "") -> dict:
    if not context and 252 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
