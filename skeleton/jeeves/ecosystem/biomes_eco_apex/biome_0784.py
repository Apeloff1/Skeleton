"""Biome eco_apex 0784.
"""
from __future__ import annotations

ID = "biome_eco_apex_0784"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 784, "tier": 784 % 5}

def apply(context: str = "") -> dict:
    if not context and 784 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
