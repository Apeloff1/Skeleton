"""Biome peak 0399.
"""
from __future__ import annotations

ID = "biome_peak_0399"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 399, "tier": 399 % 5}

def apply(context: str = "") -> dict:
    if not context and 399 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
