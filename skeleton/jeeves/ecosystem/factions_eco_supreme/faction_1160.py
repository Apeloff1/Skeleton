"""Faction eco_supreme 1160.
"""
from __future__ import annotations

ID = "faction_eco_supreme_1160"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1160, "tier": 1160 % 5}

def apply(context: str = "") -> dict:
    if not context and 1160 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
