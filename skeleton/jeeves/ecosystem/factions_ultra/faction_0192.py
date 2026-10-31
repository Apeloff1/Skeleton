"""Faction ultra 0192.
"""
from __future__ import annotations

ID = "faction_ultra_0192"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 192, "tier": 192 % 5}

def apply(context: str = "") -> dict:
    if not context and 192 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
