"""Biome ultra_max 0438.
"""
from __future__ import annotations

ID = "biome_ultra_max_0438"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 438, "tier": 438 % 5}

def apply(context: str = "") -> dict:
    if not context and 438 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
