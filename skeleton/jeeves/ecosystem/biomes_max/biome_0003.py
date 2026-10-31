"""Biome max 0003.
"""
from __future__ import annotations

ID = "biome_max_0003"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 3, "tier": 3 % 5}

def apply(context: str = "") -> dict:
    if not context and 3 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
