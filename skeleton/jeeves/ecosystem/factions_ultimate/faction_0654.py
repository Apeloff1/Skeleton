"""Faction ultimate 0654.
"""
from __future__ import annotations

ID = "faction_ultimate_0654"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 654, "tier": 654 % 5}

def apply(context: str = "") -> dict:
    if not context and 654 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
