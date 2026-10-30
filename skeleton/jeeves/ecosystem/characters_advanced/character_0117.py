"""Character advanced 0117.
"""
from __future__ import annotations

ID = "character_adv_0117"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 117, "tier": 117 % 5}

def apply(context: str = "") -> dict:
    if not context and 117 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
