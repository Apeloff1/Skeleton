"""Character scale 0051.
"""
from __future__ import annotations

ID = "character_scale_0051"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 51, "tier": 51 % 5}

def apply(context: str = "") -> dict:
    if not context and 51 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
