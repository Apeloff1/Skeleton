"""Biome supreme 0629.
"""
from __future__ import annotations

ID = "biome_supreme_0629"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 629, "tier": 629 % 5}

def apply(context: str = "") -> dict:
    if not context and 629 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
