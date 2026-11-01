"""Character ultra_max 0626.
"""
from __future__ import annotations

ID = "character_ultra_max_0626"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 626, "tier": 626 % 5}

def apply(context: str = "") -> dict:
    if not context and 626 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
