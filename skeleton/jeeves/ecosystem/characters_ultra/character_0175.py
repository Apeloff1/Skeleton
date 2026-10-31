"""Character ultra 0175.
"""
from __future__ import annotations

ID = "character_ultra_0175"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 175, "tier": 175 % 5}

def apply(context: str = "") -> dict:
    if not context and 175 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
