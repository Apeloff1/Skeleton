"""Character ultimate 0875.
"""
from __future__ import annotations

ID = "character_ultimate_0875"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 875, "tier": 875 % 5}

def apply(context: str = "") -> dict:
    if not context and 875 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
