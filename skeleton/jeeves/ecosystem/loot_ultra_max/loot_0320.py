"""Loot ultra_max 0320.
"""
from __future__ import annotations

ID = "loot_ultra_max_0320"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 320}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
