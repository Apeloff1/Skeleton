"""Loot mega 0044.
"""
from __future__ import annotations

ID = "loot_mega_0044"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 44}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
