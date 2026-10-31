"""Faction ultra 0251.
"""
from __future__ import annotations

ID = "faction_ultra_0251"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 251, "tier": 251 % 5}

def apply(context: str = "") -> dict:
    if not context and 251 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
