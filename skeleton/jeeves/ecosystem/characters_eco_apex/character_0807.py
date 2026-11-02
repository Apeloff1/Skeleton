"""Character eco_apex 0807.
"""
from __future__ import annotations

ID = "character_eco_apex_0807"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 807, "tier": 807 % 5}

def apply(context: str = "") -> dict:
    if not context and 807 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
