"""Character eco_supreme 1287.
"""
from __future__ import annotations

ID = "character_eco_supreme_1287"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1287, "tier": 1287 % 5}

def apply(context: str = "") -> dict:
    if not context and 1287 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
