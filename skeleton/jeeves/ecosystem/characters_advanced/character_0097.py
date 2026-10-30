"""Character advanced 0097.
"""
from __future__ import annotations

ID = "character_adv_0097"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 97, "tier": 97 % 5}

def apply(context: str = "") -> dict:
    if not context and 97 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
