"""Faction eco_apex 0996.
"""
from __future__ import annotations

ID = "faction_eco_apex_0996"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 996, "tier": 996 % 5}

def apply(context: str = "") -> dict:
    if not context and 996 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
