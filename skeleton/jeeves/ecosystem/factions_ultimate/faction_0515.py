"""Faction ultimate 0515.
"""
from __future__ import annotations

ID = "faction_ultimate_0515"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 515, "tier": 515 % 5}

def apply(context: str = "") -> dict:
    if not context and 515 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
