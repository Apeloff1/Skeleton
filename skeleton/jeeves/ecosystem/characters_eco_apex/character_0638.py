"""Character eco_apex 0638.
"""
from __future__ import annotations

ID = "character_eco_apex_0638"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 638, "tier": 638 % 5}

def apply(context: str = "") -> dict:
    if not context and 638 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
