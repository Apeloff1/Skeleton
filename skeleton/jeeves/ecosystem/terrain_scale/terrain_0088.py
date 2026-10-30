"""Terrain scale 0088.
"""
from __future__ import annotations

ID = "terrain_scale_0088"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 88, "tier": 88 % 5}

def apply(context: str = "") -> dict:
    if not context and 88 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
