"""Terrain scale 0148.
"""
from __future__ import annotations

ID = "terrain_scale_0148"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 148, "tier": 148 % 5}

def apply(context: str = "") -> dict:
    if not context and 148 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
