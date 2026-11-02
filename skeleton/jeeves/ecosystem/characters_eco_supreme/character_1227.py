"""Character eco_supreme 1227.
"""
from __future__ import annotations

ID = "character_eco_supreme_1227"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1227, "tier": 1227 % 5}

def apply(context: str = "") -> dict:
    if not context and 1227 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
