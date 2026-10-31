"""Character ultra 0133.
"""
from __future__ import annotations

ID = "character_ultra_0133"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 133, "tier": 133 % 5}

def apply(context: str = "") -> dict:
    if not context and 133 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
