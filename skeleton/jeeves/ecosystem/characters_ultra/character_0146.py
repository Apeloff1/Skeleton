"""Character ultra 0146.
"""
from __future__ import annotations

ID = "character_ultra_0146"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 146, "tier": 146 % 5}

def apply(context: str = "") -> dict:
    if not context and 146 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
