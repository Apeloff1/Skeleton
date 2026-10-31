"""Faction peak 0312.
"""
from __future__ import annotations

ID = "faction_peak_0312"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 312, "tier": 312 % 5}

def apply(context: str = "") -> dict:
    if not context and 312 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
