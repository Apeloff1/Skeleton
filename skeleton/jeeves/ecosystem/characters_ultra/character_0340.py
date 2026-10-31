"""Character ultra 0340.
"""
from __future__ import annotations

ID = "character_ultra_0340"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 340, "tier": 340 % 5}

def apply(context: str = "") -> dict:
    if not context and 340 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
