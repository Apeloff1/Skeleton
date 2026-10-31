"""Faction ultra 0223.
"""
from __future__ import annotations

ID = "faction_ultra_0223"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 223, "tier": 223 % 5}

def apply(context: str = "") -> dict:
    if not context and 223 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
