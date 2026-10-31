"""Loot max 0162.
"""
from __future__ import annotations

ID = "loot_max_0162"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 162}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
