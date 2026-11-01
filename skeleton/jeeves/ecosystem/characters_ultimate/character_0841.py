"""Character ultimate 0841.
"""
from __future__ import annotations

ID = "character_ultimate_0841"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 841, "tier": 841 % 5}

def apply(context: str = "") -> dict:
    if not context and 841 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
