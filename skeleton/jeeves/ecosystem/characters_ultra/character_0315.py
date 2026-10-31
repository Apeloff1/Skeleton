"""Character ultra 0315.
"""
from __future__ import annotations

ID = "character_ultra_0315"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 315, "tier": 315 % 5}

def apply(context: str = "") -> dict:
    if not context and 315 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
