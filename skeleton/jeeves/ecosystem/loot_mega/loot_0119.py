"""Loot mega 0119.
"""
from __future__ import annotations

ID = "loot_mega_0119"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 119}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
