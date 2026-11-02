"""Faction eco_apex 0591.
"""
from __future__ import annotations

ID = "faction_eco_apex_0591"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 591, "tier": 591 % 5}

def apply(context: str = "") -> dict:
    if not context and 591 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
