"""Character advanced 0105.
"""
from __future__ import annotations

ID = "character_adv_0105"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 105, "tier": 105 % 5}

def apply(context: str = "") -> dict:
    if not context and 105 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
