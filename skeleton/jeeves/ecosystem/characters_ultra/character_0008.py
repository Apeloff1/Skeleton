"""Character ultra 0008.
"""
from __future__ import annotations

ID = "character_ultra_0008"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 8, "tier": 8 % 5}

def apply(context: str = "") -> dict:
    if not context and 8 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
