"""Terrain scale 0049.
"""
from __future__ import annotations

ID = "terrain_scale_0049"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 49, "tier": 49 % 5}

def apply(context: str = "") -> dict:
    if not context and 49 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
