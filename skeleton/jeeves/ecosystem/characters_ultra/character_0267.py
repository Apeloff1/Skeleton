"""Character ultra 0267.
"""
from __future__ import annotations

ID = "character_ultra_0267"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 267, "tier": 267 % 5}

def apply(context: str = "") -> dict:
    if not context and 267 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
