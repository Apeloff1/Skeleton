"""Character ultra_max 0474.
"""
from __future__ import annotations

ID = "character_ultra_max_0474"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 474, "tier": 474 % 5}

def apply(context: str = "") -> dict:
    if not context and 474 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
