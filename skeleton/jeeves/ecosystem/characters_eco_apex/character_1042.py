"""Character eco_apex 1042.
"""
from __future__ import annotations

ID = "character_eco_apex_1042"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1042, "tier": 1042 % 5}

def apply(context: str = "") -> dict:
    if not context and 1042 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
