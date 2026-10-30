"""Loot mega 0114.
"""
from __future__ import annotations

ID = "loot_mega_0114"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 114}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
