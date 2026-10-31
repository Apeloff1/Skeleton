"""Faction max 0321.
"""
from __future__ import annotations

ID = "faction_max_0321"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 321, "tier": 321 % 5}

def apply(context: str = "") -> dict:
    if not context and 321 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
