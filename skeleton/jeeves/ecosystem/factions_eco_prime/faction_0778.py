"""Faction eco_prime 0778.
"""
from __future__ import annotations

ID = "faction_eco_prime_0778"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 778, "tier": 778 % 5}

def apply(context: str = "") -> dict:
    if not context and 778 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
