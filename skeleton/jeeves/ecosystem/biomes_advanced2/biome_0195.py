"""Biome advanced 0195.
"""
from __future__ import annotations

ID = "biome_adv_0195"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 195, "tier": 195 % 5}

def apply(context: str = "") -> dict:
    if not context and 195 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
