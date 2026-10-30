"""Character scale 0122.
"""
from __future__ import annotations

ID = "character_scale_0122"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 122, "tier": 122 % 5}

def apply(context: str = "") -> dict:
    if not context and 122 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
