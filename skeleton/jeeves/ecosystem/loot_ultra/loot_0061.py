"""Loot ultra 0061.
"""
from __future__ import annotations

ID = "loot_ultra_0061"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 61}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
