"""Biome advanced 0147.
"""
from __future__ import annotations

ID = "biome_adv_0147"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 147, "tier": 147 % 5}

def apply(context: str = "") -> dict:
    if not context and 147 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
