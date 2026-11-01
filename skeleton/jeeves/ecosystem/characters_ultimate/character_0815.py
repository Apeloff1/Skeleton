"""Character ultimate 0815.
"""
from __future__ import annotations

ID = "character_ultimate_0815"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 815, "tier": 815 % 5}

def apply(context: str = "") -> dict:
    if not context and 815 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
