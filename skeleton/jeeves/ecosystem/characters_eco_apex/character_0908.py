"""Character eco_apex 0908.
"""
from __future__ import annotations

ID = "character_eco_apex_0908"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 908, "tier": 908 % 5}

def apply(context: str = "") -> dict:
    if not context and 908 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
