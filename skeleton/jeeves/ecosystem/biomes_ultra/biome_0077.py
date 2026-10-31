"""Biome ultra 0077.
"""
from __future__ import annotations

ID = "biome_ultra_0077"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 77, "tier": 77 % 5}

def apply(context: str = "") -> dict:
    if not context and 77 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
