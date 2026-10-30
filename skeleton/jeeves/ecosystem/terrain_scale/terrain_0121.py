"""Terrain scale 0121.
"""
from __future__ import annotations

ID = "terrain_scale_0121"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 121, "tier": 121 % 5}

def apply(context: str = "") -> dict:
    if not context and 121 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
