"""Loot ultra 0118.
"""
from __future__ import annotations

ID = "loot_ultra_0118"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 118}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
