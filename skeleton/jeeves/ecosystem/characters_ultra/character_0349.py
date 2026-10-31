"""Character ultra 0349.
"""
from __future__ import annotations

ID = "character_ultra_0349"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 349, "tier": 349 % 5}

def apply(context: str = "") -> dict:
    if not context and 349 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
