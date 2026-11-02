"""Character eco_supreme 0854.
"""
from __future__ import annotations

ID = "character_eco_supreme_0854"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 854, "tier": 854 % 5}

def apply(context: str = "") -> dict:
    if not context and 854 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
