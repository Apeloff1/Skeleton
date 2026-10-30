"""Loot mega 0012.
"""
from __future__ import annotations

ID = "loot_mega_0012"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 12}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
