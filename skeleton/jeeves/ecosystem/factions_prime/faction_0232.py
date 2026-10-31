"""Faction prime 0232.
"""
from __future__ import annotations

ID = "faction_prime_0232"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 232, "tier": 232 % 5}

def apply(context: str = "") -> dict:
    if not context and 232 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
