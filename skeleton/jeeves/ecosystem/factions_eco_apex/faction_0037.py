"""Faction eco_apex 0037.
"""
from __future__ import annotations

ID = "faction_eco_apex_0037"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 37, "tier": 37 % 5}

def apply(context: str = "") -> dict:
    if not context and 37 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
