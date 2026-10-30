"""Loot mega 0078.
"""
from __future__ import annotations

ID = "loot_mega_0078"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 78}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
