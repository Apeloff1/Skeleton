"""Biome apex 0406.
"""
from __future__ import annotations

ID = "biome_apex_0406"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 406, "tier": 406 % 5}

def apply(context: str = "") -> dict:
    if not context and 406 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
