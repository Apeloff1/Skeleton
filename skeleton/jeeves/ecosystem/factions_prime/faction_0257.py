"""Faction prime 0257.
"""
from __future__ import annotations

ID = "faction_prime_0257"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 257, "tier": 257 % 5}

def apply(context: str = "") -> dict:
    if not context and 257 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
