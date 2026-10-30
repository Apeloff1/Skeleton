"""Character scale 0115.
"""
from __future__ import annotations

ID = "character_scale_0115"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 115, "tier": 115 % 5}

def apply(context: str = "") -> dict:
    if not context and 115 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
