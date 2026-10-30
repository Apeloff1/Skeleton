"""Loot mega 0111.
"""
from __future__ import annotations

ID = "loot_mega_0111"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 111}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
