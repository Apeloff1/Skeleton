"""Biome peak 0284.
"""
from __future__ import annotations

ID = "biome_peak_0284"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 284, "tier": 284 % 5}

def apply(context: str = "") -> dict:
    if not context and 284 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
