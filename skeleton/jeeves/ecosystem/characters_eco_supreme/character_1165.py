"""Character eco_supreme 1165.
"""
from __future__ import annotations

ID = "character_eco_supreme_1165"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 1165, "tier": 1165 % 5}

def apply(context: str = "") -> dict:
    if not context and 1165 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
