"""Loot ultra 0103.
"""
from __future__ import annotations

ID = "loot_ultra_0103"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 103}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
