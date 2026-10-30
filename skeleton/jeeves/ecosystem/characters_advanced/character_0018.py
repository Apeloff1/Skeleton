"""Character advanced 0018.
"""
from __future__ import annotations

ID = "character_adv_0018"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 18, "tier": 18 % 5}

def apply(context: str = "") -> dict:
    if not context and 18 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
