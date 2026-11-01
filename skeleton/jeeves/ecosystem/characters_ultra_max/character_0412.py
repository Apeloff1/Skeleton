"""Character ultra_max 0412.
"""
from __future__ import annotations

ID = "character_ultra_max_0412"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 412, "tier": 412 % 5}

def apply(context: str = "") -> dict:
    if not context and 412 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
