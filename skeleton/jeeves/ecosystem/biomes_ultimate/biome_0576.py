"""Biome ultimate 0576.
"""
from __future__ import annotations

ID = "biome_ultimate_0576"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 576, "tier": 576 % 5}

def apply(context: str = "") -> dict:
    if not context and 576 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
