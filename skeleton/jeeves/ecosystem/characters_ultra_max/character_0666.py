"""Character ultra_max 0666.
"""
from __future__ import annotations

ID = "character_ultra_max_0666"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 666, "tier": 666 % 5}

def apply(context: str = "") -> dict:
    if not context and 666 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
