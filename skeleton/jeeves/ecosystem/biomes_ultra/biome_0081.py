"""Biome ultra 0081.
"""
from __future__ import annotations

ID = "biome_ultra_0081"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 81, "tier": 81 % 5}

def apply(context: str = "") -> dict:
    if not context and 81 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
