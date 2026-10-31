"""Loot ultra 0137.
"""
from __future__ import annotations

ID = "loot_ultra_0137"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 137}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
