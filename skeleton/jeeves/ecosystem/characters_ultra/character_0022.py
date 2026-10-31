"""Character ultra 0022.
"""
from __future__ import annotations

ID = "character_ultra_0022"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 22, "tier": 22 % 5}

def apply(context: str = "") -> dict:
    if not context and 22 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
