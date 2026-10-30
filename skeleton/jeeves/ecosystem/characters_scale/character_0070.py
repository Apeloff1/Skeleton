"""Character scale 0070.
"""
from __future__ import annotations

ID = "character_scale_0070"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 70, "tier": 70 % 5}

def apply(context: str = "") -> dict:
    if not context and 70 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
