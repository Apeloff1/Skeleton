"""Biome ultra 0289.
"""
from __future__ import annotations

ID = "biome_ultra_0289"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 289, "tier": 289 % 5}

def apply(context: str = "") -> dict:
    if not context and 289 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
