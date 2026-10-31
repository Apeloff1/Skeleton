"""Biome peak 0347.
"""
from __future__ import annotations

ID = "biome_peak_0347"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 347, "tier": 347 % 5}

def apply(context: str = "") -> dict:
    if not context and 347 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
