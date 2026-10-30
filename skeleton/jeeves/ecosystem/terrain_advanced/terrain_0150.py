"""Terrain advanced 0150.
"""
from __future__ import annotations

ID = "terrain_adv_0150"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 150, "tier": 150 % 5}

def apply(context: str = "") -> dict:
    if not context and 150 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
