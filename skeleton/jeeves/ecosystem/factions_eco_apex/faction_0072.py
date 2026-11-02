"""Faction eco_apex 0072.
"""
from __future__ import annotations

ID = "faction_eco_apex_0072"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 72, "tier": 72 % 5}

def apply(context: str = "") -> dict:
    if not context and 72 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
