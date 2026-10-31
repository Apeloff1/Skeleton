"""Biome ultra 0215.
"""
from __future__ import annotations

ID = "biome_ultra_0215"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 215, "tier": 215 % 5}

def apply(context: str = "") -> dict:
    if not context and 215 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
