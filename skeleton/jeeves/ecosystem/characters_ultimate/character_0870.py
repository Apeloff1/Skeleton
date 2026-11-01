"""Character ultimate 0870.
"""
from __future__ import annotations

ID = "character_ultimate_0870"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 870, "tier": 870 % 5}

def apply(context: str = "") -> dict:
    if not context and 870 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
