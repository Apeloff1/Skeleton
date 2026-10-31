"""Biome ultra 0246.
"""
from __future__ import annotations

ID = "biome_ultra_0246"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 246, "tier": 246 % 5}

def apply(context: str = "") -> dict:
    if not context and 246 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
