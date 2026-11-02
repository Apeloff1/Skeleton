"""Faction eco_peak 0560.
"""
from __future__ import annotations

ID = "faction_eco_peak_0560"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 560, "tier": 560 % 5}

def apply(context: str = "") -> dict:
    if not context and 560 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
