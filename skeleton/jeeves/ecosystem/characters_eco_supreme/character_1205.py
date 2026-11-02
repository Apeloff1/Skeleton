"""Character eco_supreme 1205.
"""
from __future__ import annotations

ID = "character_eco_supreme_1205"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1205, "tier": 1205 % 5}

def apply(context: str = "") -> dict:
    if not context and 1205 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
