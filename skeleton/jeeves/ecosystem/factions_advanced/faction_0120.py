"""Faction advanced 0120.
"""
from __future__ import annotations

ID = "faction_adv_0120"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 120, "tier": 120 % 5}

def apply(context: str = "") -> dict:
    if not context and 120 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
