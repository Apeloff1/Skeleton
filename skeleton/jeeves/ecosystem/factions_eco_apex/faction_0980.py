"""Faction eco_apex 0980.
"""
from __future__ import annotations

ID = "faction_eco_apex_0980"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 980, "tier": 980 % 5}

def apply(context: str = "") -> dict:
    if not context and 980 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
