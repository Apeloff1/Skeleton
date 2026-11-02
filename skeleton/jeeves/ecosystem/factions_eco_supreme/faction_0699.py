"""Faction eco_supreme 0699.
"""
from __future__ import annotations

ID = "faction_eco_supreme_0699"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 699, "tier": 699 % 5}

def apply(context: str = "") -> dict:
    if not context and 699 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
