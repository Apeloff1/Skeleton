"""Faction ultimate 0433.
"""
from __future__ import annotations

ID = "faction_ultimate_0433"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 433, "tier": 433 % 5}

def apply(context: str = "") -> dict:
    if not context and 433 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
