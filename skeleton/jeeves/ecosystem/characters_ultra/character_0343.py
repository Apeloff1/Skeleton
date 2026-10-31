"""Character ultra 0343.
"""
from __future__ import annotations

ID = "character_ultra_0343"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 343, "tier": 343 % 5}

def apply(context: str = "") -> dict:
    if not context and 343 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
