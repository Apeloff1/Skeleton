"""Biome ultra 0259.
"""
from __future__ import annotations

ID = "biome_ultra_0259"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 259, "tier": 259 % 5}

def apply(context: str = "") -> dict:
    if not context and 259 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
