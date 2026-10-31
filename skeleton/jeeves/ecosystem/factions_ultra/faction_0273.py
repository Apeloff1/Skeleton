"""Faction ultra 0273.
"""
from __future__ import annotations

ID = "faction_ultra_0273"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 273, "tier": 273 % 5}

def apply(context: str = "") -> dict:
    if not context and 273 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
