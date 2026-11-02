"""Character eco_apex 0986.
"""
from __future__ import annotations

ID = "character_eco_apex_0986"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 986, "tier": 986 % 5}

def apply(context: str = "") -> dict:
    if not context and 986 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
