"""Loot ultra 0143.
"""
from __future__ import annotations

ID = "loot_ultra_0143"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 143}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
