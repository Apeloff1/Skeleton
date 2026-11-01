"""Character ultra_max 0636.
"""
from __future__ import annotations

ID = "character_ultra_max_0636"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 636, "tier": 636 % 5}

def apply(context: str = "") -> dict:
    if not context and 636 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
