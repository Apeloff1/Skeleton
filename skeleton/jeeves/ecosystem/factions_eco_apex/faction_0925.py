"""Faction eco_apex 0925.
"""
from __future__ import annotations

ID = "faction_eco_apex_0925"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 925, "tier": 925 % 5}

def apply(context: str = "") -> dict:
    if not context and 925 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
