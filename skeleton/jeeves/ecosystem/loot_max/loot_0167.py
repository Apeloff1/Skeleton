"""Loot max 0167.
"""
from __future__ import annotations

ID = "loot_max_0167"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 167}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
