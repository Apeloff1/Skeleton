"""Biome ultra 0220.
"""
from __future__ import annotations

ID = "biome_ultra_0220"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 220, "tier": 220 % 5}

def apply(context: str = "") -> dict:
    if not context and 220 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
