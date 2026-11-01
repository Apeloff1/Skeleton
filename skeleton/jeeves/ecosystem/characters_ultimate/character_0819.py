"""Character ultimate 0819.
"""
from __future__ import annotations

ID = "character_ultimate_0819"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 819, "tier": 819 % 5}

def apply(context: str = "") -> dict:
    if not context and 819 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
