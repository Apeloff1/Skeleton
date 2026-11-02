"""Character eco_apex 1040.
"""
from __future__ import annotations

ID = "character_eco_apex_1040"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1040, "tier": 1040 % 5}

def apply(context: str = "") -> dict:
    if not context and 1040 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
