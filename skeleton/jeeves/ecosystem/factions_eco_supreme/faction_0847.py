"""Faction eco_supreme 0847.
"""
from __future__ import annotations

ID = "faction_eco_supreme_0847"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 847, "tier": 847 % 5}

def apply(context: str = "") -> dict:
    if not context and 847 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
