"""Character advanced 0076.
"""
from __future__ import annotations

ID = "character_adv_0076"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 76, "tier": 76 % 5}

def apply(context: str = "") -> dict:
    if not context and 76 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
