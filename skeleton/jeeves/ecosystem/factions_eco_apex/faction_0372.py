"""Faction eco_apex 0372.
"""
from __future__ import annotations

ID = "faction_eco_apex_0372"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 372, "tier": 372 % 5}

def apply(context: str = "") -> dict:
    if not context and 372 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
