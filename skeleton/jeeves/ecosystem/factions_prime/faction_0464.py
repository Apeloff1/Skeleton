"""Faction prime 0464.
"""
from __future__ import annotations

ID = "faction_prime_0464"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 464, "tier": 464 % 5}

def apply(context: str = "") -> dict:
    if not context and 464 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
