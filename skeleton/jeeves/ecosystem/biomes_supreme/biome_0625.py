"""Biome supreme 0625.
"""
from __future__ import annotations

ID = "biome_supreme_0625"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 625, "tier": 625 % 5}

def apply(context: str = "") -> dict:
    if not context and 625 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
