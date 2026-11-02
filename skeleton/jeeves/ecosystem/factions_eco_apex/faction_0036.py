"""Faction eco_apex 0036.
"""
from __future__ import annotations

ID = "faction_eco_apex_0036"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 36, "tier": 36 % 5}

def apply(context: str = "") -> dict:
    if not context and 36 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
