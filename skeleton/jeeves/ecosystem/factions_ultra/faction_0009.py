"""Faction ultra 0009.
"""
from __future__ import annotations

ID = "faction_ultra_0009"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 9, "tier": 9 % 5}

def apply(context: str = "") -> dict:
    if not context and 9 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
