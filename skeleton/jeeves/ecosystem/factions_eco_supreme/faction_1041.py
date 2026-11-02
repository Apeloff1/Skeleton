"""Faction eco_supreme 1041.
"""
from __future__ import annotations

ID = "faction_eco_supreme_1041"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1041, "tier": 1041 % 5}

def apply(context: str = "") -> dict:
    if not context and 1041 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
