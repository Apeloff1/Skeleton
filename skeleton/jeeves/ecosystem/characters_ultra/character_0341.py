"""Character ultra 0341.
"""
from __future__ import annotations

ID = "character_ultra_0341"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 341, "tier": 341 % 5}

def apply(context: str = "") -> dict:
    if not context and 341 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
