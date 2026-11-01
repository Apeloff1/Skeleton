"""Character ultimate 0498.
"""
from __future__ import annotations

ID = "character_ultimate_0498"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 498, "tier": 498 % 5}

def apply(context: str = "") -> dict:
    if not context and 498 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
