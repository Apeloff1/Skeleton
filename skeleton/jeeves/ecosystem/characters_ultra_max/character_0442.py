"""Character ultra_max 0442.
"""
from __future__ import annotations

ID = "character_ultra_max_0442"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 442, "tier": 442 % 5}

def apply(context: str = "") -> dict:
    if not context and 442 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
