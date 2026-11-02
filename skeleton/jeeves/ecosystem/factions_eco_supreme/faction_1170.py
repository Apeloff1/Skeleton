"""Faction eco_supreme 1170.
"""
from __future__ import annotations

ID = "faction_eco_supreme_1170"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1170, "tier": 1170 % 5}

def apply(context: str = "") -> dict:
    if not context and 1170 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
