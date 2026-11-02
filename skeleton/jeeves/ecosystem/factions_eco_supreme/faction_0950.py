"""Faction eco_supreme 0950.
"""
from __future__ import annotations

ID = "faction_eco_supreme_0950"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 950, "tier": 950 % 5}

def apply(context: str = "") -> dict:
    if not context and 950 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
