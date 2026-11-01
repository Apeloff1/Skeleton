"""Character ultra_max 0677.
"""
from __future__ import annotations

ID = "character_ultra_max_0677"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 677, "tier": 677 % 5}

def apply(context: str = "") -> dict:
    if not context and 677 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
