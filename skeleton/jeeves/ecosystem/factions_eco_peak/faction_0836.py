"""Faction eco_peak 0836.
"""
from __future__ import annotations

ID = "faction_eco_peak_0836"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 836, "tier": 836 % 5}

def apply(context: str = "") -> dict:
    if not context and 836 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
