"""Loot ultra 0053.
"""
from __future__ import annotations

ID = "loot_ultra_0053"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 53}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
