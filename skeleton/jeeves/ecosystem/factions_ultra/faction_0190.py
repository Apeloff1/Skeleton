"""Faction ultra 0190.
"""
from __future__ import annotations

ID = "faction_ultra_0190"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 190, "tier": 190 % 5}

def apply(context: str = "") -> dict:
    if not context and 190 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
