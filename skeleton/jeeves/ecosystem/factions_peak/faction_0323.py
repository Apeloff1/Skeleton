"""Faction peak 0323.
"""
from __future__ import annotations

ID = "faction_peak_0323"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 323, "tier": 323 % 5}

def apply(context: str = "") -> dict:
    if not context and 323 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
