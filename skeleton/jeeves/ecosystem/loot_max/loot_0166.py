"""Loot max 0166.
"""
from __future__ import annotations

ID = "loot_max_0166"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 166}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
