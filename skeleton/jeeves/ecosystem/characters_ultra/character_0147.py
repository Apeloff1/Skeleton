"""Character ultra 0147.
"""
from __future__ import annotations

ID = "character_ultra_0147"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 147, "tier": 147 % 5}

def apply(context: str = "") -> dict:
    if not context and 147 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
