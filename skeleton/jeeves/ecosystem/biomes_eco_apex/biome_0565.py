"""Biome eco_apex 0565.
"""
from __future__ import annotations

ID = "biome_eco_apex_0565"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 565, "tier": 565 % 5}

def apply(context: str = "") -> dict:
    if not context and 565 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
