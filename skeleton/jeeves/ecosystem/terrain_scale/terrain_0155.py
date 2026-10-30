"""Terrain scale 0155.
"""
from __future__ import annotations

ID = "terrain_scale_0155"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 155, "tier": 155 % 5}

def apply(context: str = "") -> dict:
    if not context and 155 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
