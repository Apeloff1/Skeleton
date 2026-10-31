"""Loot ultra 0069.
"""
from __future__ import annotations

ID = "loot_ultra_0069"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 69}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
