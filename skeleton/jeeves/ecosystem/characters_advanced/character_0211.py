"""Character advanced 0211.
"""
from __future__ import annotations

ID = "character_adv_0211"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 211, "tier": 211 % 5}

def apply(context: str = "") -> dict:
    if not context and 211 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
