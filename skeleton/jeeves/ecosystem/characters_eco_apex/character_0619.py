"""Character eco_apex 0619.
"""
from __future__ import annotations

ID = "character_eco_apex_0619"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 619, "tier": 619 % 5}

def apply(context: str = "") -> dict:
    if not context and 619 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
