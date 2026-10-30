"""Character advanced 0173.
"""
from __future__ import annotations

ID = "character_adv_0173"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 173, "tier": 173 % 5}

def apply(context: str = "") -> dict:
    if not context and 173 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
