"""Loot max 0153.
"""
from __future__ import annotations

ID = "loot_max_0153"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 153}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
