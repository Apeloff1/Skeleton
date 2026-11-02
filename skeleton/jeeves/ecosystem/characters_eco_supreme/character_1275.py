"""Character eco_supreme 1275.
"""
from __future__ import annotations

ID = "character_eco_supreme_1275"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1275, "tier": 1275 % 5}

def apply(context: str = "") -> dict:
    if not context and 1275 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
