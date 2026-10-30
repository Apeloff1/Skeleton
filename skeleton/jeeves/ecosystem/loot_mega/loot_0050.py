"""Loot mega 0050.
"""
from __future__ import annotations

ID = "loot_mega_0050"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 50}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
