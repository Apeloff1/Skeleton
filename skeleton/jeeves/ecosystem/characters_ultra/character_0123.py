"""Character ultra 0123.
"""
from __future__ import annotations

ID = "character_ultra_0123"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 123, "tier": 123 % 5}

def apply(context: str = "") -> dict:
    if not context and 123 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
