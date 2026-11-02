"""Faction eco_supreme 1124.
"""
from __future__ import annotations

ID = "faction_eco_supreme_1124"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1124, "tier": 1124 % 5}

def apply(context: str = "") -> dict:
    if not context and 1124 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
