"""Faction eco_supreme 1074.
"""
from __future__ import annotations

ID = "faction_eco_supreme_1074"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1074, "tier": 1074 % 5}

def apply(context: str = "") -> dict:
    if not context and 1074 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
