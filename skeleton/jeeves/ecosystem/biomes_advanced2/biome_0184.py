"""Biome advanced 0184.
"""
from __future__ import annotations

ID = "biome_adv_0184"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 184, "tier": 184 % 5}

def apply(context: str = "") -> dict:
    if not context and 184 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
