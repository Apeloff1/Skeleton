"""Character eco_apex 1021.
"""
from __future__ import annotations

ID = "character_eco_apex_1021"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1021, "tier": 1021 % 5}

def apply(context: str = "") -> dict:
    if not context and 1021 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
