"""Loot ultra 0136.
"""
from __future__ import annotations

ID = "loot_ultra_0136"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 136}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
