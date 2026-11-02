"""Faction eco_apex 0883.
"""
from __future__ import annotations

ID = "faction_eco_apex_0883"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 883, "tier": 883 % 5}

def apply(context: str = "") -> dict:
    if not context and 883 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
