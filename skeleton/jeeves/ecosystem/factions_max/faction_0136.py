"""Faction max 0136.
"""
from __future__ import annotations

ID = "faction_max_0136"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 136, "tier": 136 % 5}

def apply(context: str = "") -> dict:
    if not context and 136 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
