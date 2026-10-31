"""Character ultra 0337.
"""
from __future__ import annotations

ID = "character_ultra_0337"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 337, "tier": 337 % 5}

def apply(context: str = "") -> dict:
    if not context and 337 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
