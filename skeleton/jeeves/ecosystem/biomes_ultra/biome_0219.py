"""Biome ultra 0219.
"""
from __future__ import annotations

ID = "biome_ultra_0219"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 219, "tier": 219 % 5}

def apply(context: str = "") -> dict:
    if not context and 219 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
