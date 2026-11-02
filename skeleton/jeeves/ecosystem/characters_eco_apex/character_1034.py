"""Character eco_apex 1034.
"""
from __future__ import annotations

ID = "character_eco_apex_1034"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1034, "tier": 1034 % 5}

def apply(context: str = "") -> dict:
    if not context and 1034 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
