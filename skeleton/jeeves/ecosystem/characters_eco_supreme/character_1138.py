"""Character eco_supreme 1138.
"""
from __future__ import annotations

ID = "character_eco_supreme_1138"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1138, "tier": 1138 % 5}

def apply(context: str = "") -> dict:
    if not context and 1138 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
