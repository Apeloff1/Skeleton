"""Character ultra 0297.
"""
from __future__ import annotations

ID = "character_ultra_0297"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 297, "tier": 297 % 5}

def apply(context: str = "") -> dict:
    if not context and 297 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
