"""Biome advanced 0166.
"""
from __future__ import annotations

ID = "biome_adv_0166"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 166, "tier": 166 % 5}

def apply(context: str = "") -> dict:
    if not context and 166 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
