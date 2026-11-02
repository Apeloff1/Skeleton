"""Character eco_apex 0605.
"""
from __future__ import annotations

ID = "character_eco_apex_0605"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 605, "tier": 605 % 5}

def apply(context: str = "") -> dict:
    if not context and 605 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
