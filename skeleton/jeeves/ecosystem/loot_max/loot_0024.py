"""Loot max 0024.
"""
from __future__ import annotations

ID = "loot_max_0024"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 24}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
