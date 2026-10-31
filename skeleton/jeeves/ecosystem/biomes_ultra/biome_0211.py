"""Biome ultra 0211.
"""
from __future__ import annotations

ID = "biome_ultra_0211"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 211, "tier": 211 % 5}

def apply(context: str = "") -> dict:
    if not context and 211 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
