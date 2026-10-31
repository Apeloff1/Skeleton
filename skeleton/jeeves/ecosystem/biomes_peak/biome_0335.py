"""Biome peak 0335.
"""
from __future__ import annotations

ID = "biome_peak_0335"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 335, "tier": 335 % 5}

def apply(context: str = "") -> dict:
    if not context and 335 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
