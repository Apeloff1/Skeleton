"""Terrain scale 0080.
"""
from __future__ import annotations

ID = "terrain_scale_0080"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 80, "tier": 80 % 5}

def apply(context: str = "") -> dict:
    if not context and 80 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
