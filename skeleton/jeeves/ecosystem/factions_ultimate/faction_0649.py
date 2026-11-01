"""Faction ultimate 0649.
"""
from __future__ import annotations

ID = "faction_ultimate_0649"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 649, "tier": 649 % 5}

def apply(context: str = "") -> dict:
    if not context and 649 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
