"""Character max 0395.
"""
from __future__ import annotations

ID = "character_max_0395"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 395, "tier": 395 % 5}

def apply(context: str = "") -> dict:
    if not context and 395 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
