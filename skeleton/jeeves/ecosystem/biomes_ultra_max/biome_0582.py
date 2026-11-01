"""Biome ultra_max 0582.
"""
from __future__ import annotations

ID = "biome_ultra_max_0582"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 582, "tier": 582 % 5}

def apply(context: str = "") -> dict:
    if not context and 582 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
