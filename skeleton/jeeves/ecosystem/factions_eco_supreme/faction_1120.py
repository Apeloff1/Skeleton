"""Faction eco_supreme 1120.
"""
from __future__ import annotations

ID = "faction_eco_supreme_1120"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1120, "tier": 1120 % 5}

def apply(context: str = "") -> dict:
    if not context and 1120 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
