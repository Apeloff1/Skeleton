"""Biome advanced 0158.
"""
from __future__ import annotations

ID = "biome_adv_0158"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 158, "tier": 158 % 5}

def apply(context: str = "") -> dict:
    if not context and 158 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
