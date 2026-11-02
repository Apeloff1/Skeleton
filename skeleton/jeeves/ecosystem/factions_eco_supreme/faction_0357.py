"""Faction eco_supreme 0357.
"""
from __future__ import annotations

ID = "faction_eco_supreme_0357"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 357, "tier": 357 % 5}

def apply(context: str = "") -> dict:
    if not context and 357 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
