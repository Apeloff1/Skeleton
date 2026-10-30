"""Terrain advanced 0035.
"""
from __future__ import annotations

ID = "terrain_adv_0035"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 35, "tier": 35 % 5}

def apply(context: str = "") -> dict:
    if not context and 35 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
