"""Faction eco_supreme 1027.
"""
from __future__ import annotations

ID = "faction_eco_supreme_1027"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1027, "tier": 1027 % 5}

def apply(context: str = "") -> dict:
    if not context and 1027 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
