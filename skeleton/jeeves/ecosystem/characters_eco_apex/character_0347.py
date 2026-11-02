"""Character eco_apex 0347.
"""
from __future__ import annotations

ID = "character_eco_apex_0347"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 347, "tier": 347 % 5}

def apply(context: str = "") -> dict:
    if not context and 347 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
