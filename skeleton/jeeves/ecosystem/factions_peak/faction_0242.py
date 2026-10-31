"""Faction peak 0242.
"""
from __future__ import annotations

ID = "faction_peak_0242"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 242, "tier": 242 % 5}

def apply(context: str = "") -> dict:
    if not context and 242 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
