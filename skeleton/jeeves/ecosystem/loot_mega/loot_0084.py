"""Loot mega 0084.
"""
from __future__ import annotations

ID = "loot_mega_0084"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 84}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
