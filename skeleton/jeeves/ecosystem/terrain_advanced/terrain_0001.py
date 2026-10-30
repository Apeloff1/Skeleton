"""Terrain advanced 0001.
"""
from __future__ import annotations

ID = "terrain_adv_0001"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 1, "tier": 1 % 5}

def apply(context: str = "") -> dict:
    if not context and 1 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
