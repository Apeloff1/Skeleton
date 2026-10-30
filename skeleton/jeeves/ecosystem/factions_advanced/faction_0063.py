"""Faction advanced 0063.
"""
from __future__ import annotations

ID = "faction_adv_0063"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 63, "tier": 63 % 5}

def apply(context: str = "") -> dict:
    if not context and 63 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
