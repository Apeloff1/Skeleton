"""Character ultra_max 0415.
"""
from __future__ import annotations

ID = "character_ultra_max_0415"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 415, "tier": 415 % 5}

def apply(context: str = "") -> dict:
    if not context and 415 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
