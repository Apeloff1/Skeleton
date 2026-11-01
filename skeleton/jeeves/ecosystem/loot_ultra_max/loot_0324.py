"""Loot ultra_max 0324.
"""
from __future__ import annotations

ID = "loot_ultra_max_0324"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 324}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
