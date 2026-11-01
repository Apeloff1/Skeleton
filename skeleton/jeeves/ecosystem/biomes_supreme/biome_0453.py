"""Biome supreme 0453.
"""
from __future__ import annotations

ID = "biome_supreme_0453"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 453, "tier": 453 % 5}

def apply(context: str = "") -> dict:
    if not context and 453 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
