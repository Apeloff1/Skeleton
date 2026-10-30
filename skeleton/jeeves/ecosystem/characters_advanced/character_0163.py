"""Character advanced 0163.
"""
from __future__ import annotations

ID = "character_adv_0163"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 163, "tier": 163 % 5}

def apply(context: str = "") -> dict:
    if not context and 163 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
