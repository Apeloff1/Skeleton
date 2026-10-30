"""Terrain scale 0097.
"""
from __future__ import annotations

ID = "terrain_scale_0097"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 97, "tier": 97 % 5}

def apply(context: str = "") -> dict:
    if not context and 97 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
