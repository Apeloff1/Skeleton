"""Biome ultra 0151.
"""
from __future__ import annotations

ID = "biome_ultra_0151"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 151, "tier": 151 % 5}

def apply(context: str = "") -> dict:
    if not context and 151 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
