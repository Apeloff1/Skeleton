"""Character scale 0102.
"""
from __future__ import annotations

ID = "character_scale_0102"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 102, "tier": 102 % 5}

def apply(context: str = "") -> dict:
    if not context and 102 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
