"""Loot ultra 0132.
"""
from __future__ import annotations

ID = "loot_ultra_0132"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 132}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
