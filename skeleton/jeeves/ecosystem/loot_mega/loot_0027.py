"""Loot mega 0027.
"""
from __future__ import annotations

ID = "loot_mega_0027"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 27}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
