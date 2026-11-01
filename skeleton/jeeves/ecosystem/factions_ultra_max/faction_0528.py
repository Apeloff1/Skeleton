"""Faction ultra_max 0528.
"""
from __future__ import annotations

ID = "faction_ultra_max_0528"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 528, "tier": 528 % 5}

def apply(context: str = "") -> dict:
    if not context and 528 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
