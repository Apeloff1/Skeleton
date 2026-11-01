"""Loot ultra_max 0304.
"""
from __future__ import annotations

ID = "loot_ultra_max_0304"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 304}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
