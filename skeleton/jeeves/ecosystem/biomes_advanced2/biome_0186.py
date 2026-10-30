"""Biome advanced 0186.
"""
from __future__ import annotations

ID = "biome_adv_0186"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 186, "tier": 186 % 5}

def apply(context: str = "") -> dict:
    if not context and 186 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
