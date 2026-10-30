"""Terrain scale 0098.
"""
from __future__ import annotations

ID = "terrain_scale_0098"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 98, "tier": 98 % 5}

def apply(context: str = "") -> dict:
    if not context and 98 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
