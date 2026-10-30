"""Biome advanced 0109.
"""
from __future__ import annotations

ID = "biome_adv_0109"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 109, "tier": 109 % 5}

def apply(context: str = "") -> dict:
    if not context and 109 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
