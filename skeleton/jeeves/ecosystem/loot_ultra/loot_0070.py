"""Loot ultra 0070.
"""
from __future__ import annotations

ID = "loot_ultra_0070"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 70}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
