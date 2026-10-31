"""Biome peak 0365.
"""
from __future__ import annotations

ID = "biome_peak_0365"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 365, "tier": 365 % 5}

def apply(context: str = "") -> dict:
    if not context and 365 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
