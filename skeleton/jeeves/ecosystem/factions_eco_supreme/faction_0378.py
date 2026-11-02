"""Faction eco_supreme 0378.
"""
from __future__ import annotations

ID = "faction_eco_supreme_0378"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 378, "tier": 378 % 5}

def apply(context: str = "") -> dict:
    if not context and 378 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
