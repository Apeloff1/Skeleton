"""Character ultimate 0713.
"""
from __future__ import annotations

ID = "character_ultimate_0713"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 713, "tier": 713 % 5}

def apply(context: str = "") -> dict:
    if not context and 713 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
