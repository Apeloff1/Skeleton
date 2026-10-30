"""Character scale 0200.
"""
from __future__ import annotations

ID = "character_scale_0200"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 200, "tier": 200 % 5}

def apply(context: str = "") -> dict:
    if not context and 200 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
