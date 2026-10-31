"""Loot ultra 0074.
"""
from __future__ import annotations

ID = "loot_ultra_0074"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 74}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
