"""Character ultra 0167.
"""
from __future__ import annotations

ID = "character_ultra_0167"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 167, "tier": 167 % 5}

def apply(context: str = "") -> dict:
    if not context and 167 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
