"""Biome ultra 0033.
"""
from __future__ import annotations

ID = "biome_ultra_0033"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 33, "tier": 33 % 5}

def apply(context: str = "") -> dict:
    if not context and 33 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
