"""Faction eco_supreme 0947.
"""
from __future__ import annotations

ID = "faction_eco_supreme_0947"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 947, "tier": 947 % 5}

def apply(context: str = "") -> dict:
    if not context and 947 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
