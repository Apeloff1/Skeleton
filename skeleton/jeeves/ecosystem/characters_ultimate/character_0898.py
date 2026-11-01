"""Character ultimate 0898.
"""
from __future__ import annotations

ID = "character_ultimate_0898"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 898, "tier": 898 % 5}

def apply(context: str = "") -> dict:
    if not context and 898 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
