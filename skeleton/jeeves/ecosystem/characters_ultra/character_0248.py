"""Character ultra 0248.
"""
from __future__ import annotations

ID = "character_ultra_0248"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 248, "tier": 248 % 5}

def apply(context: str = "") -> dict:
    if not context and 248 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
