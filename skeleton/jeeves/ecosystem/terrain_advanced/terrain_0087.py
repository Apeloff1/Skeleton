"""Terrain advanced 0087.
"""
from __future__ import annotations

ID = "terrain_adv_0087"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 87, "tier": 87 % 5}

def apply(context: str = "") -> dict:
    if not context and 87 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
