"""Faction eco_prime 0440.
"""
from __future__ import annotations

ID = "faction_eco_prime_0440"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 440, "tier": 440 % 5}

def apply(context: str = "") -> dict:
    if not context and 440 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
