"""Terrain scale 0014.
"""
from __future__ import annotations

ID = "terrain_scale_0014"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 14, "tier": 14 % 5}

def apply(context: str = "") -> dict:
    if not context and 14 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
