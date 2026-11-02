"""Character eco_apex 0683.
"""
from __future__ import annotations

ID = "character_eco_apex_0683"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 683, "tier": 683 % 5}

def apply(context: str = "") -> dict:
    if not context and 683 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
