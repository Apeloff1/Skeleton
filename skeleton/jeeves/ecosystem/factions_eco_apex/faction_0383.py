"""Faction eco_apex 0383.
"""
from __future__ import annotations

ID = "faction_eco_apex_0383"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 383, "tier": 383 % 5}

def apply(context: str = "") -> dict:
    if not context and 383 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
