"""Faction ultra 0159.
"""
from __future__ import annotations

ID = "faction_ultra_0159"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 159, "tier": 159 % 5}

def apply(context: str = "") -> dict:
    if not context and 159 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
