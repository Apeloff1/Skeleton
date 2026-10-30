"""Terrain advanced 0084.
"""
from __future__ import annotations

ID = "terrain_adv_0084"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 84, "tier": 84 % 5}

def apply(context: str = "") -> dict:
    if not context and 84 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
