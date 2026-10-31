"""Biome peak 0373.
"""
from __future__ import annotations

ID = "biome_peak_0373"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 373, "tier": 373 % 5}

def apply(context: str = "") -> dict:
    if not context and 373 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
