"""Character scale 0087.
"""
from __future__ import annotations

ID = "character_scale_0087"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 87, "tier": 87 % 5}

def apply(context: str = "") -> dict:
    if not context and 87 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
