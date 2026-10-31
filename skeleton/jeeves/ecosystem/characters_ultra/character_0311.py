"""Character ultra 0311.
"""
from __future__ import annotations

ID = "character_ultra_0311"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 311, "tier": 311 % 5}

def apply(context: str = "") -> dict:
    if not context and 311 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
