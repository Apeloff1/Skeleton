"""Character ultra 0321.
"""
from __future__ import annotations

ID = "character_ultra_0321"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 321, "tier": 321 % 5}

def apply(context: str = "") -> dict:
    if not context and 321 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
