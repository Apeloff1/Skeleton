"""Faction eco_apex 0375.
"""
from __future__ import annotations

ID = "faction_eco_apex_0375"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 375, "tier": 375 % 5}

def apply(context: str = "") -> dict:
    if not context and 375 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
