"""Loot mega 0030.
"""
from __future__ import annotations

ID = "loot_mega_0030"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 30}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
