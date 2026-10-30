"""Character scale 0235.
"""
from __future__ import annotations

ID = "character_scale_0235"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 235, "tier": 235 % 5}

def apply(context: str = "") -> dict:
    if not context and 235 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
