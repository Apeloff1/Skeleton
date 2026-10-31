"""Loot ultra 0140.
"""
from __future__ import annotations

ID = "loot_ultra_0140"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 140}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
