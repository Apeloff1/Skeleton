"""Loot ultra 0010.
"""
from __future__ import annotations

ID = "loot_ultra_0010"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 10}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
