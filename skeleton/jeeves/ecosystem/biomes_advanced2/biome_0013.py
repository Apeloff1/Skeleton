"""Biome advanced 0013.
"""
from __future__ import annotations

ID = "biome_adv_0013"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 13, "tier": 13 % 5}

def apply(context: str = "") -> dict:
    if not context and 13 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
