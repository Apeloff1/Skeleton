"""Faction max 0316.
"""
from __future__ import annotations

ID = "faction_max_0316"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 316, "tier": 316 % 5}

def apply(context: str = "") -> dict:
    if not context and 316 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
