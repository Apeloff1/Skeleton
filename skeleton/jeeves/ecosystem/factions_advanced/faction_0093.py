"""Faction advanced 0093.
"""
from __future__ import annotations

ID = "faction_adv_0093"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 93, "tier": 93 % 5}

def apply(context: str = "") -> dict:
    if not context and 93 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
