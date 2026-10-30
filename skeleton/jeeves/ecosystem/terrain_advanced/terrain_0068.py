"""Terrain advanced 0068.
"""
from __future__ import annotations

ID = "terrain_adv_0068"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 68, "tier": 68 % 5}

def apply(context: str = "") -> dict:
    if not context and 68 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
