"""Character advanced 0057.
"""
from __future__ import annotations

ID = "character_adv_0057"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 57, "tier": 57 % 5}

def apply(context: str = "") -> dict:
    if not context and 57 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
