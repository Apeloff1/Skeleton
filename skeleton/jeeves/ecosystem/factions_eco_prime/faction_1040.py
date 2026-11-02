"""Faction eco_prime 1040.
"""
from __future__ import annotations

ID = "faction_eco_prime_1040"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1040, "tier": 1040 % 5}

def apply(context: str = "") -> dict:
    if not context and 1040 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
