"""Faction eco_prime 0825.
"""
from __future__ import annotations

ID = "faction_eco_prime_0825"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 825, "tier": 825 % 5}

def apply(context: str = "") -> dict:
    if not context and 825 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
