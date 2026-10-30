"""Character scale 0157.
"""
from __future__ import annotations

ID = "character_scale_0157"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 157, "tier": 157 % 5}

def apply(context: str = "") -> dict:
    if not context and 157 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
