"""Terrain advanced 0124.
"""
from __future__ import annotations

ID = "terrain_adv_0124"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 124, "tier": 124 % 5}

def apply(context: str = "") -> dict:
    if not context and 124 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
