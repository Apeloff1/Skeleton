"""Character scale 0203.
"""
from __future__ import annotations

ID = "character_scale_0203"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 203, "tier": 203 % 5}

def apply(context: str = "") -> dict:
    if not context and 203 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
