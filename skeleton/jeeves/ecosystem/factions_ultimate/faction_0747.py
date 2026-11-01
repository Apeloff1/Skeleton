"""Faction ultimate 0747.
"""
from __future__ import annotations

ID = "faction_ultimate_0747"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 747, "tier": 747 % 5}

def apply(context: str = "") -> dict:
    if not context and 747 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
