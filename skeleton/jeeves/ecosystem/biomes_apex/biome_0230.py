"""Biome apex 0230.
"""
from __future__ import annotations

ID = "biome_apex_0230"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 230, "tier": 230 % 5}

def apply(context: str = "") -> dict:
    if not context and 230 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
