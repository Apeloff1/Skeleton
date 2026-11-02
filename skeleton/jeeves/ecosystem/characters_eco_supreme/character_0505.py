"""Character eco_supreme 0505.
"""
from __future__ import annotations

ID = "character_eco_supreme_0505"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 505, "tier": 505 % 5}

def apply(context: str = "") -> dict:
    if not context and 505 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
