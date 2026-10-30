"""Biome advanced 0187.
"""
from __future__ import annotations

ID = "biome_adv_0187"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 187, "tier": 187 % 5}

def apply(context: str = "") -> dict:
    if not context and 187 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
