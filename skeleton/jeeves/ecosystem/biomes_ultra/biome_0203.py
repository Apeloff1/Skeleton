"""Biome ultra 0203.
"""
from __future__ import annotations

ID = "biome_ultra_0203"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 203, "tier": 203 % 5}

def apply(context: str = "") -> dict:
    if not context and 203 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
