"""Loot ultra 0094.
"""
from __future__ import annotations

ID = "loot_ultra_0094"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 94}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
