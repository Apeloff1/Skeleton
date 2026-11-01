"""Faction ultra_max 0306.
"""
from __future__ import annotations

ID = "faction_ultra_max_0306"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 306, "tier": 306 % 5}

def apply(context: str = "") -> dict:
    if not context and 306 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
