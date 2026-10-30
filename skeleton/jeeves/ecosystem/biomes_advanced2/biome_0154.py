"""Biome advanced 0154.
"""
from __future__ import annotations

ID = "biome_adv_0154"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 154, "tier": 154 % 5}

def apply(context: str = "") -> dict:
    if not context and 154 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
