"""Character advanced 0066.
"""
from __future__ import annotations

ID = "character_adv_0066"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 66, "tier": 66 % 5}

def apply(context: str = "") -> dict:
    if not context and 66 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
