"""Character ultra_max 0588.
"""
from __future__ import annotations

ID = "character_ultra_max_0588"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 588, "tier": 588 % 5}

def apply(context: str = "") -> dict:
    if not context and 588 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
