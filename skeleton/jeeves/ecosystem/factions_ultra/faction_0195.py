"""Faction ultra 0195.
"""
from __future__ import annotations

ID = "faction_ultra_0195"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 195, "tier": 195 % 5}

def apply(context: str = "") -> dict:
    if not context and 195 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
