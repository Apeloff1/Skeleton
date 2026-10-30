"""Character scale 0073.
"""
from __future__ import annotations

ID = "character_scale_0073"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 73, "tier": 73 % 5}

def apply(context: str = "") -> dict:
    if not context and 73 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
