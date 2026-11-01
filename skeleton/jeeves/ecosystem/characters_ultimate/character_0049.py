"""Character ultimate 0049.
"""
from __future__ import annotations

ID = "character_ultimate_0049"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 49, "tier": 49 % 5}

def apply(context: str = "") -> dict:
    if not context and 49 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
