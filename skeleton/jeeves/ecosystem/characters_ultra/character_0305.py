"""Character ultra 0305.
"""
from __future__ import annotations

ID = "character_ultra_0305"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 305, "tier": 305 % 5}

def apply(context: str = "") -> dict:
    if not context and 305 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
