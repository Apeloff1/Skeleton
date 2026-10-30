"""Biome advanced 0134.
"""
from __future__ import annotations

ID = "biome_adv_0134"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 134, "tier": 134 % 5}

def apply(context: str = "") -> dict:
    if not context and 134 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
