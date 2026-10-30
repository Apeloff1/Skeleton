"""Biome advanced 0116.
"""
from __future__ import annotations

ID = "biome_adv_0116"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 116, "tier": 116 % 5}

def apply(context: str = "") -> dict:
    if not context and 116 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
