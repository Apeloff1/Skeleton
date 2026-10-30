"""Character scale 0238.
"""
from __future__ import annotations

ID = "character_scale_0238"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 238, "tier": 238 % 5}

def apply(context: str = "") -> dict:
    if not context and 238 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
