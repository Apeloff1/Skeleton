"""Character eco_apex 0309.
"""
from __future__ import annotations

ID = "character_eco_apex_0309"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 309, "tier": 309 % 5}

def apply(context: str = "") -> dict:
    if not context and 309 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
