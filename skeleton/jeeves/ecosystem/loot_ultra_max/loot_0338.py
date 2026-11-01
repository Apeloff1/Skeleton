"""Loot ultra_max 0338.
"""
from __future__ import annotations

ID = "loot_ultra_max_0338"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 338}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
