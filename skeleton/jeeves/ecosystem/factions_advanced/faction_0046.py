"""Faction advanced 0046.
"""
from __future__ import annotations

ID = "faction_adv_0046"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 46, "tier": 46 % 5}

def apply(context: str = "") -> dict:
    if not context and 46 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
