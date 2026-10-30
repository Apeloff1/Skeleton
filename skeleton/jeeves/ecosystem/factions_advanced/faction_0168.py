"""Faction advanced 0168.
"""
from __future__ import annotations

ID = "faction_adv_0168"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 168, "tier": 168 % 5}

def apply(context: str = "") -> dict:
    if not context and 168 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
