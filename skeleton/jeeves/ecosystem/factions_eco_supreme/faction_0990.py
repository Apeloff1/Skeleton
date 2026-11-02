"""Faction eco_supreme 0990.
"""
from __future__ import annotations

ID = "faction_eco_supreme_0990"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 990, "tier": 990 % 5}

def apply(context: str = "") -> dict:
    if not context and 990 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
