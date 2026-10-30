"""Terrain scale 0166.
"""
from __future__ import annotations

ID = "terrain_scale_0166"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 166, "tier": 166 % 5}

def apply(context: str = "") -> dict:
    if not context and 166 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
