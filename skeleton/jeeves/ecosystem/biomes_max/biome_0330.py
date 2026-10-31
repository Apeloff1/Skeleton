"""Biome max 0330.
"""
from __future__ import annotations

ID = "biome_max_0330"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 330, "tier": 330 % 5}

def apply(context: str = "") -> dict:
    if not context and 330 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
