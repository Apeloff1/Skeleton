"""Biome supreme 0654.
"""
from __future__ import annotations

ID = "biome_supreme_0654"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 654, "tier": 654 % 5}

def apply(context: str = "") -> dict:
    if not context and 654 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
