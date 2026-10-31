"""Biome apex 0017.
"""
from __future__ import annotations

ID = "biome_apex_0017"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 17, "tier": 17 % 5}

def apply(context: str = "") -> dict:
    if not context and 17 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
