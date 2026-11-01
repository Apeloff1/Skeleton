"""Character ultimate 0664.
"""
from __future__ import annotations

ID = "character_ultimate_0664"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 664, "tier": 664 % 5}

def apply(context: str = "") -> dict:
    if not context and 664 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
