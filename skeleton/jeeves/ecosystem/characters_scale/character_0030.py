"""Character scale 0030.
"""
from __future__ import annotations

ID = "character_scale_0030"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 30, "tier": 30 % 5}

def apply(context: str = "") -> dict:
    if not context and 30 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
