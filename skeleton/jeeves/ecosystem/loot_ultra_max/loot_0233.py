"""Loot ultra_max 0233.
"""
from __future__ import annotations

ID = "loot_ultra_max_0233"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 233}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
