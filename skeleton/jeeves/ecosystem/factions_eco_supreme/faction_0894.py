"""Faction eco_supreme 0894.
"""
from __future__ import annotations

ID = "faction_eco_supreme_0894"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 894, "tier": 894 % 5}

def apply(context: str = "") -> dict:
    if not context and 894 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
