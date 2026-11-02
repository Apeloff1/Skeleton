"""Faction eco_supreme 0875.
"""
from __future__ import annotations

ID = "faction_eco_supreme_0875"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 875, "tier": 875 % 5}

def apply(context: str = "") -> dict:
    if not context and 875 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
