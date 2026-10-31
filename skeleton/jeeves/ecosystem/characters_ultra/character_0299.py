"""Character ultra 0299.
"""
from __future__ import annotations

ID = "character_ultra_0299"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 299, "tier": 299 % 5}

def apply(context: str = "") -> dict:
    if not context and 299 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
