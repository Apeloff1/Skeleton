"""Faction ultra 0287.
"""
from __future__ import annotations

ID = "faction_ultra_0287"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 287, "tier": 287 % 5}

def apply(context: str = "") -> dict:
    if not context and 287 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
