"""Terrain advanced 0139.
"""
from __future__ import annotations

ID = "terrain_adv_0139"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 139, "tier": 139 % 5}

def apply(context: str = "") -> dict:
    if not context and 139 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
