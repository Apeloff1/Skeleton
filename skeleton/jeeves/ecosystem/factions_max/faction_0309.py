"""Faction max 0309.
"""
from __future__ import annotations

ID = "faction_max_0309"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 309, "tier": 309 % 5}

def apply(context: str = "") -> dict:
    if not context and 309 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
