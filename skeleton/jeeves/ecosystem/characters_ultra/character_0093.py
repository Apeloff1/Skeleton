"""Character ultra 0093.
"""
from __future__ import annotations

ID = "character_ultra_0093"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 93, "tier": 93 % 5}

def apply(context: str = "") -> dict:
    if not context and 93 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
