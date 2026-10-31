"""Biome peak 0126.
"""
from __future__ import annotations

ID = "biome_peak_0126"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 126, "tier": 126 % 5}

def apply(context: str = "") -> dict:
    if not context and 126 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
