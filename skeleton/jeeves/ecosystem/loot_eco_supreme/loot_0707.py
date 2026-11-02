"""Loot eco_supreme 0707.
"""
from __future__ import annotations

ID = "loot_eco_supreme_0707"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 707}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
