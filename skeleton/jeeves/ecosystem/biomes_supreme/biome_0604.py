"""Biome supreme 0604.
"""
from __future__ import annotations

ID = "biome_supreme_0604"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 604, "tier": 604 % 5}

def apply(context: str = "") -> dict:
    if not context and 604 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
