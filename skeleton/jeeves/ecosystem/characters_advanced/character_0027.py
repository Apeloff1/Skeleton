"""Character advanced 0027.
"""
from __future__ import annotations

ID = "character_adv_0027"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 27, "tier": 27 % 5}

def apply(context: str = "") -> dict:
    if not context and 27 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
