"""Character eco_supreme 1297.
"""
from __future__ import annotations

ID = "character_eco_supreme_1297"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1297, "tier": 1297 % 5}

def apply(context: str = "") -> dict:
    if not context and 1297 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
