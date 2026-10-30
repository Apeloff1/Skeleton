"""Biome advanced 0005.
"""
from __future__ import annotations

ID = "biome_adv_0005"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 5, "tier": 5 % 5}

def apply(context: str = "") -> dict:
    if not context and 5 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
