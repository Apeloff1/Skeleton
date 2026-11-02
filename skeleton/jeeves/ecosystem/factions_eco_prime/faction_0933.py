"""Faction eco_prime 0933.
"""
from __future__ import annotations

ID = "faction_eco_prime_0933"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 933, "tier": 933 % 5}

def apply(context: str = "") -> dict:
    if not context and 933 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
