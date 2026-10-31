"""Biome ultra 0042.
"""
from __future__ import annotations

ID = "biome_ultra_0042"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 42, "tier": 42 % 5}

def apply(context: str = "") -> dict:
    if not context and 42 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
