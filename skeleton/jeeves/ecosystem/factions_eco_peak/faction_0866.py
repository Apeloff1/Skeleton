"""Faction eco_peak 0866.
"""
from __future__ import annotations

ID = "faction_eco_peak_0866"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 866, "tier": 866 % 5}

def apply(context: str = "") -> dict:
    if not context and 866 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
