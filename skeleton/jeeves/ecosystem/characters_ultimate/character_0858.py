"""Character ultimate 0858.
"""
from __future__ import annotations

ID = "character_ultimate_0858"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 858, "tier": 858 % 5}

def apply(context: str = "") -> dict:
    if not context and 858 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
