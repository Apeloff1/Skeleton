"""Character eco_apex 0222.
"""
from __future__ import annotations

ID = "character_eco_apex_0222"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 222, "tier": 222 % 5}

def apply(context: str = "") -> dict:
    if not context and 222 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
