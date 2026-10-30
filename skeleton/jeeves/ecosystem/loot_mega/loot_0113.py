"""Loot mega 0113.
"""
from __future__ import annotations

ID = "loot_mega_0113"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 113}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
