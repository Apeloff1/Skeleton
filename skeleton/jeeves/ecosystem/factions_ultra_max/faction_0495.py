"""Faction ultra_max 0495.
"""
from __future__ import annotations

ID = "faction_ultra_max_0495"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 495, "tier": 495 % 5}

def apply(context: str = "") -> dict:
    if not context and 495 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
