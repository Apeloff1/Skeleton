"""Biome advanced 0060.
"""
from __future__ import annotations

ID = "biome_adv_0060"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 60, "tier": 60 % 5}

def apply(context: str = "") -> dict:
    if not context and 60 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
