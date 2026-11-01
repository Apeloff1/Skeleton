"""Loot ultra_max 0342.
"""
from __future__ import annotations

ID = "loot_ultra_max_0342"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 342}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
