"""Faction eco_apex 0777.
"""
from __future__ import annotations

ID = "faction_eco_apex_0777"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 777, "tier": 777 % 5}

def apply(context: str = "") -> dict:
    if not context and 777 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
