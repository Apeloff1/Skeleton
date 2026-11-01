"""Faction ultimate 0710.
"""
from __future__ import annotations

ID = "faction_ultimate_0710"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 710, "tier": 710 % 5}

def apply(context: str = "") -> dict:
    if not context and 710 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
