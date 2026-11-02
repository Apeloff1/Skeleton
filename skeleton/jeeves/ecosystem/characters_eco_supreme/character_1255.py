"""Character eco_supreme 1255.
"""
from __future__ import annotations

ID = "character_eco_supreme_1255"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1255, "tier": 1255 % 5}

def apply(context: str = "") -> dict:
    if not context and 1255 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
