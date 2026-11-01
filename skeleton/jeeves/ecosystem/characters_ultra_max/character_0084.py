"""Character ultra_max 0084.
"""
from __future__ import annotations

ID = "character_ultra_max_0084"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 84, "tier": 84 % 5}

def apply(context: str = "") -> dict:
    if not context and 84 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
