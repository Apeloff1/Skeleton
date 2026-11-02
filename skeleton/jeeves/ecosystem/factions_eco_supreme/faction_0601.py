"""Faction eco_supreme 0601.
"""
from __future__ import annotations

ID = "faction_eco_supreme_0601"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 601, "tier": 601 % 5}

def apply(context: str = "") -> dict:
    if not context and 601 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
