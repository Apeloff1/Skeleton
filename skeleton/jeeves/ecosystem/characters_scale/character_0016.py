"""Character scale 0016.
"""
from __future__ import annotations

ID = "character_scale_0016"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 16, "tier": 16 % 5}

def apply(context: str = "") -> dict:
    if not context and 16 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
