"""Faction ultra 0164.
"""
from __future__ import annotations

ID = "faction_ultra_0164"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 164, "tier": 164 % 5}

def apply(context: str = "") -> dict:
    if not context and 164 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
