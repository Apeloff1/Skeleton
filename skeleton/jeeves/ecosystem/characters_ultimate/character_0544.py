"""Character ultimate 0544.
"""
from __future__ import annotations

ID = "character_ultimate_0544"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 544, "tier": 544 % 5}

def apply(context: str = "") -> dict:
    if not context and 544 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
