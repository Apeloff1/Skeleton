"""Loot ultra 0096.
"""
from __future__ import annotations

ID = "loot_ultra_0096"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 96}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
