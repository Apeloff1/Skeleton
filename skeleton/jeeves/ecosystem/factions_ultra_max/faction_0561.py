"""Faction ultra_max 0561.
"""
from __future__ import annotations

ID = "faction_ultra_max_0561"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 561, "tier": 561 % 5}

def apply(context: str = "") -> dict:
    if not context and 561 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
