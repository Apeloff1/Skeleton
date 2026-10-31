"""Character ultra 0165.
"""
from __future__ import annotations

ID = "character_ultra_0165"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 165, "tier": 165 % 5}

def apply(context: str = "") -> dict:
    if not context and 165 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
