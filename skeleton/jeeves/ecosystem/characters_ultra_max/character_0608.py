"""Character ultra_max 0608.
"""
from __future__ import annotations

ID = "character_ultra_max_0608"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 608, "tier": 608 % 5}

def apply(context: str = "") -> dict:
    if not context and 608 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
