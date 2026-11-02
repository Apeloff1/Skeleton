"""Faction eco_apex 0951.
"""
from __future__ import annotations

ID = "faction_eco_apex_0951"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 951, "tier": 951 % 5}

def apply(context: str = "") -> dict:
    if not context and 951 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
