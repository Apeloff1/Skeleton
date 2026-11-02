"""Character eco_apex 0800.
"""
from __future__ import annotations

ID = "character_eco_apex_0800"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 800, "tier": 800 % 5}

def apply(context: str = "") -> dict:
    if not context and 800 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
