"""Biome ultra 0153.
"""
from __future__ import annotations

ID = "biome_ultra_0153"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 153, "tier": 153 % 5}

def apply(context: str = "") -> dict:
    if not context and 153 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
