"""Character scale 0089.
"""
from __future__ import annotations

ID = "character_scale_0089"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 89, "tier": 89 % 5}

def apply(context: str = "") -> dict:
    if not context and 89 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
