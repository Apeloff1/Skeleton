"""Loot mega 0049.
"""
from __future__ import annotations

ID = "loot_mega_0049"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 49}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
