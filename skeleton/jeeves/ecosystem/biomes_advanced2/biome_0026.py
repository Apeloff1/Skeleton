"""Biome advanced 0026.
"""
from __future__ import annotations

ID = "biome_adv_0026"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 26, "tier": 26 % 5}

def apply(context: str = "") -> dict:
    if not context and 26 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
