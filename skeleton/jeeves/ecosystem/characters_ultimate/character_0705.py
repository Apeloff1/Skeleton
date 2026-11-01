"""Character ultimate 0705.
"""
from __future__ import annotations

ID = "character_ultimate_0705"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 705, "tier": 705 % 5}

def apply(context: str = "") -> dict:
    if not context and 705 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
