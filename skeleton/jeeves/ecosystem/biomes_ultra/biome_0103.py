"""Biome ultra 0103.
"""
from __future__ import annotations

ID = "biome_ultra_0103"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 103, "tier": 103 % 5}

def apply(context: str = "") -> dict:
    if not context and 103 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
