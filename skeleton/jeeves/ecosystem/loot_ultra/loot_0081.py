"""Loot ultra 0081.
"""
from __future__ import annotations

ID = "loot_ultra_0081"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 81}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
