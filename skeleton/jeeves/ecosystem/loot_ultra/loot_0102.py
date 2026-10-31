"""Loot ultra 0102.
"""
from __future__ import annotations

ID = "loot_ultra_0102"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 102}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
