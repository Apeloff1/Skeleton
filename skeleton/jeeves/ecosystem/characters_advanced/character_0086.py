"""Character advanced 0086.
"""
from __future__ import annotations

ID = "character_adv_0086"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 86, "tier": 86 % 5}

def apply(context: str = "") -> dict:
    if not context and 86 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
