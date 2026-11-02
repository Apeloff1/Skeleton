"""Character eco_apex 1037.
"""
from __future__ import annotations

ID = "character_eco_apex_1037"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1037, "tier": 1037 % 5}

def apply(context: str = "") -> dict:
    if not context and 1037 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
