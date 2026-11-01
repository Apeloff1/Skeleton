"""Biome supreme 0463.
"""
from __future__ import annotations

ID = "biome_supreme_0463"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 463, "tier": 463 % 5}

def apply(context: str = "") -> dict:
    if not context and 463 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
