"""Character eco_apex 0900.
"""
from __future__ import annotations

ID = "character_eco_apex_0900"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 900, "tier": 900 % 5}

def apply(context: str = "") -> dict:
    if not context and 900 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
