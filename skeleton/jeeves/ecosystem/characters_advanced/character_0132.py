"""Character advanced 0132.
"""
from __future__ import annotations

ID = "character_adv_0132"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 132, "tier": 132 % 5}

def apply(context: str = "") -> dict:
    if not context and 132 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
