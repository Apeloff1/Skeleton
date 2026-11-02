"""Faction eco_supreme 1020.
"""
from __future__ import annotations

ID = "faction_eco_supreme_1020"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1020, "tier": 1020 % 5}

def apply(context: str = "") -> dict:
    if not context and 1020 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
