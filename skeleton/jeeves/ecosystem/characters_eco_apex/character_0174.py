"""Character eco_apex 0174.
"""
from __future__ import annotations

ID = "character_eco_apex_0174"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 174, "tier": 174 % 5}

def apply(context: str = "") -> dict:
    if not context and 174 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
