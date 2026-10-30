"""Character advanced 0202.
"""
from __future__ import annotations

ID = "character_adv_0202"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 202, "tier": 202 % 5}

def apply(context: str = "") -> dict:
    if not context and 202 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
