"""Faction advanced 0107.
"""
from __future__ import annotations

ID = "faction_adv_0107"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 107, "tier": 107 % 5}

def apply(context: str = "") -> dict:
    if not context and 107 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
