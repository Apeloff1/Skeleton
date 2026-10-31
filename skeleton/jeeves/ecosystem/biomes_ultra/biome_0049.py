"""Biome ultra 0049.
"""
from __future__ import annotations

ID = "biome_ultra_0049"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 49, "tier": 49 % 5}

def apply(context: str = "") -> dict:
    if not context and 49 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
