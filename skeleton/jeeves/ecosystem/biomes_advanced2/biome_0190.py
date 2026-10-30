"""Biome advanced 0190.
"""
from __future__ import annotations

ID = "biome_adv_0190"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 190, "tier": 190 % 5}

def apply(context: str = "") -> dict:
    if not context and 190 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
