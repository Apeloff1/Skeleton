"""Faction peak 0293.
"""
from __future__ import annotations

ID = "faction_peak_0293"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 293, "tier": 293 % 5}

def apply(context: str = "") -> dict:
    if not context and 293 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
