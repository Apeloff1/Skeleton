"""Loot mega 0036.
"""
from __future__ import annotations

ID = "loot_mega_0036"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 36}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
