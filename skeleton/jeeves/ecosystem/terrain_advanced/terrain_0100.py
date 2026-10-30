"""Terrain advanced 0100.
"""
from __future__ import annotations

ID = "terrain_adv_0100"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 100, "tier": 100 % 5}

def apply(context: str = "") -> dict:
    if not context and 100 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
