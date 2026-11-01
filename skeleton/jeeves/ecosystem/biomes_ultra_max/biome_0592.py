"""Biome ultra_max 0592.
"""
from __future__ import annotations

ID = "biome_ultra_max_0592"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 592, "tier": 592 % 5}

def apply(context: str = "") -> dict:
    if not context and 592 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
