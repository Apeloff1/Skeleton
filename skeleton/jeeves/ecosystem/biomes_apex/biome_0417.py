"""Biome apex 0417.
"""
from __future__ import annotations

ID = "biome_apex_0417"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 417, "tier": 417 % 5}

def apply(context: str = "") -> dict:
    if not context and 417 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
