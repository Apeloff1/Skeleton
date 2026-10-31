"""Biome ultra 0278.
"""
from __future__ import annotations

ID = "biome_ultra_0278"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 278, "tier": 278 % 5}

def apply(context: str = "") -> dict:
    if not context and 278 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
