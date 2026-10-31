"""Biome peak 0001.
"""
from __future__ import annotations

ID = "biome_peak_0001"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 1, "tier": 1 % 5}

def apply(context: str = "") -> dict:
    if not context and 1 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
