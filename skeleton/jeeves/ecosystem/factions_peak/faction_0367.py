"""Faction peak 0367.
"""
from __future__ import annotations

ID = "faction_peak_0367"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 367, "tier": 367 % 5}

def apply(context: str = "") -> dict:
    if not context and 367 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
