"""Character ultimate 0662.
"""
from __future__ import annotations

ID = "character_ultimate_0662"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 662, "tier": 662 % 5}

def apply(context: str = "") -> dict:
    if not context and 662 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
