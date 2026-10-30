"""Character scale 0128.
"""
from __future__ import annotations

ID = "character_scale_0128"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 128, "tier": 128 % 5}

def apply(context: str = "") -> dict:
    if not context and 128 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
