"""Faction max 0270.
"""
from __future__ import annotations

ID = "faction_max_0270"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 270, "tier": 270 % 5}

def apply(context: str = "") -> dict:
    if not context and 270 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
