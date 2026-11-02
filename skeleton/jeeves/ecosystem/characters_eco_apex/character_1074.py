"""Character eco_apex 1074.
"""
from __future__ import annotations

ID = "character_eco_apex_1074"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1074, "tier": 1074 % 5}

def apply(context: str = "") -> dict:
    if not context and 1074 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
