"""Loot mega 0115.
"""
from __future__ import annotations

ID = "loot_mega_0115"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 115}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
