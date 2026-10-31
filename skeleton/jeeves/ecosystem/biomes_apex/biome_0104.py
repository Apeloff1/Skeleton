"""Biome apex 0104.
"""
from __future__ import annotations

ID = "biome_apex_0104"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 104, "tier": 104 % 5}

def apply(context: str = "") -> dict:
    if not context and 104 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
