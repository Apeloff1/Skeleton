"""Biome ultra 0247.
"""
from __future__ import annotations

ID = "biome_ultra_0247"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 247, "tier": 247 % 5}

def apply(context: str = "") -> dict:
    if not context and 247 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
