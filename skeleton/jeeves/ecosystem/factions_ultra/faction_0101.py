"""Faction ultra 0101.
"""
from __future__ import annotations

ID = "faction_ultra_0101"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 101, "tier": 101 % 5}

def apply(context: str = "") -> dict:
    if not context and 101 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
