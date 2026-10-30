"""Terrain scale 0066.
"""
from __future__ import annotations

ID = "terrain_scale_0066"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 66, "tier": 66 % 5}

def apply(context: str = "") -> dict:
    if not context and 66 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
