"""Biome max 0293.
"""
from __future__ import annotations

ID = "biome_max_0293"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 293, "tier": 293 % 5}

def apply(context: str = "") -> dict:
    if not context and 293 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
