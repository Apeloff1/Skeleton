"""Character scale 0193.
"""
from __future__ import annotations

ID = "character_scale_0193"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 193, "tier": 193 % 5}

def apply(context: str = "") -> dict:
    if not context and 193 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
