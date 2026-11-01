"""Character ultimate 0584.
"""
from __future__ import annotations

ID = "character_ultimate_0584"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 584, "tier": 584 % 5}

def apply(context: str = "") -> dict:
    if not context and 584 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
