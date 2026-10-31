"""Biome peak 0396.
"""
from __future__ import annotations

ID = "biome_peak_0396"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 396, "tier": 396 % 5}

def apply(context: str = "") -> dict:
    if not context and 396 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
