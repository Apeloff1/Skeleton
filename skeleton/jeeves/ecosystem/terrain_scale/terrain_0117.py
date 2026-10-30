"""Terrain scale 0117.
"""
from __future__ import annotations

ID = "terrain_scale_0117"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 117, "tier": 117 % 5}

def apply(context: str = "") -> dict:
    if not context and 117 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
