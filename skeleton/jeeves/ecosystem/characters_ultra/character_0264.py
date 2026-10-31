"""Character ultra 0264.
"""
from __future__ import annotations

ID = "character_ultra_0264"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 264, "tier": 264 % 5}

def apply(context: str = "") -> dict:
    if not context and 264 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
