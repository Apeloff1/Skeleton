"""Loot ultra_max 0298.
"""
from __future__ import annotations

ID = "loot_ultra_max_0298"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 298}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
