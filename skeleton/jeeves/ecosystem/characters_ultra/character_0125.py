"""Character ultra 0125.
"""
from __future__ import annotations

ID = "character_ultra_0125"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 125, "tier": 125 % 5}

def apply(context: str = "") -> dict:
    if not context and 125 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
