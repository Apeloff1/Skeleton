"""Faction ultra 0026.
"""
from __future__ import annotations

ID = "faction_ultra_0026"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 26, "tier": 26 % 5}

def apply(context: str = "") -> dict:
    if not context and 26 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
