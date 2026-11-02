"""Faction eco_apex 0955.
"""
from __future__ import annotations

ID = "faction_eco_apex_0955"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 955, "tier": 955 % 5}

def apply(context: str = "") -> dict:
    if not context and 955 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
