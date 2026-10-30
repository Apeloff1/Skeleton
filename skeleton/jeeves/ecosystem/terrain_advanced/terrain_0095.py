"""Terrain advanced 0095.
"""
from __future__ import annotations

ID = "terrain_adv_0095"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 95, "tier": 95 % 5}

def apply(context: str = "") -> dict:
    if not context and 95 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
