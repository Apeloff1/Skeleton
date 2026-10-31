"""Faction peak 0366.
"""
from __future__ import annotations

ID = "faction_peak_0366"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 366, "tier": 366 % 5}

def apply(context: str = "") -> dict:
    if not context and 366 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
