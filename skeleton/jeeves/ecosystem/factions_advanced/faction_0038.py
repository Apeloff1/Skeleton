"""Faction advanced 0038.
"""
from __future__ import annotations

ID = "faction_adv_0038"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 38, "tier": 38 % 5}

def apply(context: str = "") -> dict:
    if not context and 38 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
