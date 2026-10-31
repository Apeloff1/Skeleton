"""Biome ultra 0185.
"""
from __future__ import annotations

ID = "biome_ultra_0185"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 185, "tier": 185 % 5}

def apply(context: str = "") -> dict:
    if not context and 185 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
