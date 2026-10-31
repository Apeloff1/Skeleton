"""Biome peak 0149.
"""
from __future__ import annotations

ID = "biome_peak_0149"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 149, "tier": 149 % 5}

def apply(context: str = "") -> dict:
    if not context and 149 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
