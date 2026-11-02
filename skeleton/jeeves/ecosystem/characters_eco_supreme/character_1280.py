"""Character eco_supreme 1280.
"""
from __future__ import annotations

ID = "character_eco_supreme_1280"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1280, "tier": 1280 % 5}

def apply(context: str = "") -> dict:
    if not context and 1280 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
