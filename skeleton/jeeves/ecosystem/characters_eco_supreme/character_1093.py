"""Character eco_supreme 1093.
"""
from __future__ import annotations

ID = "character_eco_supreme_1093"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1093, "tier": 1093 % 5}

def apply(context: str = "") -> dict:
    if not context and 1093 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
