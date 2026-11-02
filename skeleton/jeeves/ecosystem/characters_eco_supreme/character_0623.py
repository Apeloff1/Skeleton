"""Character eco_supreme 0623.
"""
from __future__ import annotations

ID = "character_eco_supreme_0623"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 623, "tier": 623 % 5}

def apply(context: str = "") -> dict:
    if not context and 623 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
