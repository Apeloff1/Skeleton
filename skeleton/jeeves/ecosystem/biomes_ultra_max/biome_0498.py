"""Biome ultra_max 0498.
"""
from __future__ import annotations

ID = "biome_ultra_max_0498"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 498, "tier": 498 % 5}

def apply(context: str = "") -> dict:
    if not context and 498 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
