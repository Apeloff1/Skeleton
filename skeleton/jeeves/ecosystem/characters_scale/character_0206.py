"""Character scale 0206.
"""
from __future__ import annotations

ID = "character_scale_0206"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 206, "tier": 206 % 5}

def apply(context: str = "") -> dict:
    if not context and 206 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
