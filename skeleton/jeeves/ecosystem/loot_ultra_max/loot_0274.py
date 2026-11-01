"""Loot ultra_max 0274.
"""
from __future__ import annotations

ID = "loot_ultra_max_0274"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 274}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
