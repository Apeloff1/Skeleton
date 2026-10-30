"""Character scale 0025.
"""
from __future__ import annotations

ID = "character_scale_0025"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 25, "tier": 25 % 5}

def apply(context: str = "") -> dict:
    if not context and 25 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
