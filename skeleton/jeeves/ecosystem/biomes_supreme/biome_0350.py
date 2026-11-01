"""Biome supreme 0350.
"""
from __future__ import annotations

ID = "biome_supreme_0350"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 350, "tier": 350 % 5}

def apply(context: str = "") -> dict:
    if not context and 350 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
