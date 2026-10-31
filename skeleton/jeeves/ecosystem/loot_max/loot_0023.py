"""Loot max 0023.
"""
from __future__ import annotations

ID = "loot_max_0023"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 23}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
