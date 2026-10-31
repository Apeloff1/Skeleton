"""Loot ultra 0019.
"""
from __future__ import annotations

ID = "loot_ultra_0019"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 19}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
