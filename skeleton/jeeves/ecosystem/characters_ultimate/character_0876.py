"""Character ultimate 0876.
"""
from __future__ import annotations

ID = "character_ultimate_0876"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 876, "tier": 876 % 5}

def apply(context: str = "") -> dict:
    if not context and 876 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
