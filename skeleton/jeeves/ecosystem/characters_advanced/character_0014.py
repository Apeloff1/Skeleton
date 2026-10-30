"""Character advanced 0014.
"""
from __future__ import annotations

ID = "character_adv_0014"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 14, "tier": 14 % 5}

def apply(context: str = "") -> dict:
    if not context and 14 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
