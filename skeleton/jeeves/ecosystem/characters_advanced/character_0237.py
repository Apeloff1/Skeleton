"""Character advanced 0237.
"""
from __future__ import annotations

ID = "character_adv_0237"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 237, "tier": 237 % 5}

def apply(context: str = "") -> dict:
    if not context and 237 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
