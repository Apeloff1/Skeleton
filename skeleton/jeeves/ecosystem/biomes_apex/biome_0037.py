"""Biome apex 0037.
"""
from __future__ import annotations

ID = "biome_apex_0037"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 37, "tier": 37 % 5}

def apply(context: str = "") -> dict:
    if not context and 37 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
