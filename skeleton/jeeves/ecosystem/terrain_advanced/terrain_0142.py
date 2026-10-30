"""Terrain advanced 0142.
"""
from __future__ import annotations

ID = "terrain_adv_0142"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 142, "tier": 142 % 5}

def apply(context: str = "") -> dict:
    if not context and 142 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
