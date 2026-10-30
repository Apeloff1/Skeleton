"""Character scale 0037.
"""
from __future__ import annotations

ID = "character_scale_0037"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 37, "tier": 37 % 5}

def apply(context: str = "") -> dict:
    if not context and 37 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
