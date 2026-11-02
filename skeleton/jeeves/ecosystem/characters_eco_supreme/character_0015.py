"""Character eco_supreme 0015.
"""
from __future__ import annotations

ID = "character_eco_supreme_0015"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 15, "tier": 15 % 5}

def apply(context: str = "") -> dict:
    if not context and 15 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
