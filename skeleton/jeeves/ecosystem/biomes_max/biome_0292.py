"""Biome max 0292.
"""
from __future__ import annotations

ID = "biome_max_0292"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 292, "tier": 292 % 5}

def apply(context: str = "") -> dict:
    if not context and 292 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
