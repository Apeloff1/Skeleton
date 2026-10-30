"""Terrain scale 0039.
"""
from __future__ import annotations

ID = "terrain_scale_0039"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 39, "tier": 39 % 5}

def apply(context: str = "") -> dict:
    if not context and 39 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
