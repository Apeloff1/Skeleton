"""Character scale 0072.
"""
from __future__ import annotations

ID = "character_scale_0072"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 72, "tier": 72 % 5}

def apply(context: str = "") -> dict:
    if not context and 72 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
