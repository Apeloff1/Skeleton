"""Loot mega 0108.
"""
from __future__ import annotations

ID = "loot_mega_0108"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 108}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
