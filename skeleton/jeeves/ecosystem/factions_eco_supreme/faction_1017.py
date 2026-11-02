"""Faction eco_supreme 1017.
"""
from __future__ import annotations

ID = "faction_eco_supreme_1017"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1017, "tier": 1017 % 5}

def apply(context: str = "") -> dict:
    if not context and 1017 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
