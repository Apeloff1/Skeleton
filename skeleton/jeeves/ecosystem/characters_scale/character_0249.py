"""Character scale 0249.
"""
from __future__ import annotations

ID = "character_scale_0249"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 249, "tier": 249 % 5}

def apply(context: str = "") -> dict:
    if not context and 249 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
