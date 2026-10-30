"""Character advanced 0153.
"""
from __future__ import annotations

ID = "character_adv_0153"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 153, "tier": 153 % 5}

def apply(context: str = "") -> dict:
    if not context and 153 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
