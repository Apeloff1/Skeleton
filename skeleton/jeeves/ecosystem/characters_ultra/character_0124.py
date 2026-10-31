"""Character ultra 0124.
"""
from __future__ import annotations

ID = "character_ultra_0124"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 124, "tier": 124 % 5}

def apply(context: str = "") -> dict:
    if not context and 124 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
