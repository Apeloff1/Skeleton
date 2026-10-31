"""Faction ultra 0193.
"""
from __future__ import annotations

ID = "faction_ultra_0193"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 193, "tier": 193 % 5}

def apply(context: str = "") -> dict:
    if not context and 193 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
