"""Character scale 0182.
"""
from __future__ import annotations

ID = "character_scale_0182"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 182, "tier": 182 % 5}

def apply(context: str = "") -> dict:
    if not context and 182 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
