"""Character eco_apex 0931.
"""
from __future__ import annotations

ID = "character_eco_apex_0931"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 931, "tier": 931 % 5}

def apply(context: str = "") -> dict:
    if not context and 931 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
