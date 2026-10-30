"""Character scale 0243.
"""
from __future__ import annotations

ID = "character_scale_0243"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 243, "tier": 243 % 5}

def apply(context: str = "") -> dict:
    if not context and 243 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
