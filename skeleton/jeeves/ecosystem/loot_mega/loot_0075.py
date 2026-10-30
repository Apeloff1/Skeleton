"""Loot mega 0075.
"""
from __future__ import annotations

ID = "loot_mega_0075"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 75}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
