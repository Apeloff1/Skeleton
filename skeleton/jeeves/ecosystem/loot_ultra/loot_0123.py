"""Loot ultra 0123.
"""
from __future__ import annotations

ID = "loot_ultra_0123"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 123}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
