"""Terrain advanced 0176.
"""
from __future__ import annotations

ID = "terrain_adv_0176"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 176, "tier": 176 % 5}

def apply(context: str = "") -> dict:
    if not context and 176 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
