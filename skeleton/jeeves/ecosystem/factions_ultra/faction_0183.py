"""Faction ultra 0183.
"""
from __future__ import annotations

ID = "faction_ultra_0183"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 183, "tier": 183 % 5}

def apply(context: str = "") -> dict:
    if not context and 183 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
