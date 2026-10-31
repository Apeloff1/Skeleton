"""Character ultra 0283.
"""
from __future__ import annotations

ID = "character_ultra_0283"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 283, "tier": 283 % 5}

def apply(context: str = "") -> dict:
    if not context and 283 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
