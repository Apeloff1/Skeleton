"""Loot ultra 0131.
"""
from __future__ import annotations

ID = "loot_ultra_0131"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 131}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
