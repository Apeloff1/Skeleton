"""Character ultimate 0493.
"""
from __future__ import annotations

ID = "character_ultimate_0493"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 493, "tier": 493 % 5}

def apply(context: str = "") -> dict:
    if not context and 493 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
