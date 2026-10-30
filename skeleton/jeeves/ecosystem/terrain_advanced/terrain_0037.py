"""Terrain advanced 0037.
"""
from __future__ import annotations

ID = "terrain_adv_0037"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 37, "tier": 37 % 5}

def apply(context: str = "") -> dict:
    if not context and 37 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
